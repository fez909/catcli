"""
author: deadc0de6 (https://github.com/deadc0de6)
Copyright (c) 2017, deadc0de6

Class that represents a node in the catalog tree
"""

import os
import anytree
import psutil
import time

# local imports
from . import __version__ as VERSION
import catcli.utils as utils
from catcli.logger import Logger
from catcli.decomp import Decomp

'''
There are 4 types of node:
    * "top" node representing the top node (generic node)
    * "storage" node representing a storage
    * "dir" node representing a directory
    * "file" node representing a file
'''


class Noder:

    TOPNAME = 'top'
    METANAME = 'meta'
    TYPE_TOP = 'top'  # tip top ;-)
    TYPE_FILE = 'file'
    TYPE_DIR = 'dir'
    TYPE_ARC = 'arc'
    TYPE_STORAGE = 'storage'
    TYPE_META = 'meta'

    def __init__(self, verbose=False, sortsize=False, arc=False):
        self.hash = True
        self.verbose = verbose
        self.sortsize = sortsize
        self.arc = arc
        if self.arc:
            self.decomp = Decomp()

    def set_hashing(self, val):
        self.hash = val

    def get_storage_names(self, top):
        ''' return a list of all storage names '''
        return [x.name for x in list(top.children)]

    def clean_storage_attr(self, attr):
        if not attr:
            return ''
        return ', '.join(attr)

    def get_node(self, top, path):
        ''' get the node at path '''
        r = anytree.resolver.Resolver('name')
        try:
            return r.get(top, path)
        except anytree.resolver.ChildResolverError:
            Logger.err('No node at path \"{}\"'.format(path))
            return None

    ###############################################################
    # node creationg
    ###############################################################
    def new_top_node(self):
        ''' create a new top node'''
        return anytree.AnyNode(name=self.TOPNAME, type=self.TYPE_TOP)

    def update_metanode(self, meta):
        ''' create or update meta node information '''
        epoch = int(time.time())
        if not meta:
            attr = {}
            attr['created'] = epoch
            attr['created_version'] = VERSION
            meta = anytree.AnyNode(name=self.METANAME, type=self.TYPE_META,
                                   attr=attr)
        meta.attr['access'] = epoch
        meta.attr['access_version'] = VERSION
        return meta

    def file_node(self, name, path, parent, storagepath):
        ''' create a new node representing a file '''
        if not os.path.exists(path):
            Logger.err('File \"{}\" does not exist'.format(path))
            return None
        path = os.path.abspath(path)
        try:
            st = os.lstat(path)
        except OSError as e:
            Logger.err('OSError: {}'.format(e))
            return None
        md5 = None
        if self.hash:
            md5 = utils.md5sum(path)
        relpath = os.path.join(os.path.basename(storagepath),
                               os.path.relpath(path, start=storagepath))

        n = self._node(name, self.TYPE_FILE, relpath, parent,
                       size=st.st_size, md5=md5)
        if self.arc:
            ext = os.path.splitext(path)[1][1:]
            if ext in self.decomp.get_format():
                names = self.decomp.get_names(path)
                self.list_to_tree(n, names)
        return n

    def dir_node(self, name, path, parent, storagepath):
        ''' create a new node representing a directory '''
        path = os.path.abspath(path)
        relpath = os.path.relpath(path, start=storagepath)
        return self._node(name, self.TYPE_DIR, relpath, parent)

    def storage_node(self, name, path, parent, attr=None):
        ''' create a new node representing a storage '''
        path = os.path.abspath(path)
        free = psutil.disk_usage(path).free
        total = psutil.disk_usage(path).total
        epoch = int(time.time())
        return anytree.AnyNode(name=name, type=self.TYPE_STORAGE, free=free,
                               total=total, parent=parent, attr=attr, ts=epoch)

    def archive_node(self, name, path, parent, archive):
        return anytree.AnyNode(name=name, type=self.TYPE_ARC, relpath=path,
                               parent=parent, size=0, md5=None,
                               archive=archive)

    def _node(self, name, type, relpath, parent, size=None, md5=None):
        ''' generic node creation '''
        return anytree.AnyNode(name=name, type=type, relpath=relpath,
                               parent=parent, size=size, md5=md5)

    ###############################################################
    # printing
    ###############################################################
    def _print_node(self, node, pre='', withpath=False,
                    withdepth=False, withstorage=False):
        ''' print a node '''
        if node.type == self.TYPE_TOP:
            Logger.out('{}{}'.format(pre, node.name))
        elif node.type == self.TYPE_FILE:
            name = node.name
            if withpath:
                name = node.relpath
            if withstorage:
                storage = self._get_storage(node)
            attr = ''
            if node.md5:
                attr = ', md5:{}'.format(node.md5)
            compl = 'size:{}{}'.format(utils.human(node.size), attr)
            if withstorage:
                compl += ', storage:{}'.format(Logger.bold(storage.name))
            Logger.file(pre, name, compl)
        elif node.type == self.TYPE_DIR:
            name = node.name
            if withpath:
                name = node.relpath
            depth = ''
            if withdepth:
                depth = len(node.children)
            if withstorage:
                storage = self._get_storage(node)
            attr = []
            if node.size:
                attr.append(['totsize', utils.human(node.size)])
            if withstorage:
                attr.append(['storage', Logger.bold(storage.name)])
            Logger.dir(pre, name, depth=depth, attr=attr)
        elif node.type == self.TYPE_STORAGE:
            hf = utils.human(node.free)
            ht = utils.human(node.total)
            name = '{} (free:{}, total:{})'.format(node.name, hf, ht)
            Logger.storage(pre, name, node.attr)
        elif node.type == self.TYPE_ARC:
            if self.arc:
                Logger.arc(pre, node.name, node.archive)
        else:
            Logger.err('Weird node encountered: {}'.format(node))
            # Logger.out('{}{}'.format(pre, node.name))

    def print_tree(self, node, style=anytree.ContRoundStyle()):
        ''' print the tree similar to unix tool "tree" '''
        rend = anytree.RenderTree(node, childiter=self._sort_tree)
        for pre, fill, node in rend:
            self._print_node(node, pre=pre, withdepth=True)

    ###############################################################
    # searching
    ###############################################################
    def find_name(self, root, key, script=False):
        ''' find files based on their names '''
        if self.verbose:
            Logger.info('searching for \"{}\"'.format(key))
        self.term = key
        found = anytree.findall(root, filter_=self._find_name)
        paths = []
        for f in found:
            if f.type == self.TYPE_STORAGE:
                # ignore storage nodes
                continue
            self._print_node(f, withpath=True, withdepth=True,
                             withstorage=True)
            paths.append(f.relpath)
        if script:
            tmp = ['${source}/' + x for x in paths]
            cmd = 'op=file; source=/media/mnt; $op {}'.format(' '.join(tmp))
            Logger.info(cmd)
        return found

    def _find_name(self, node):
        ''' callback for finding files '''
        if self.term.lower() in node.name.lower():
            return True
        return False

    ###############################################################
    # climbing
    ###############################################################
    def walk(self, root, path, rec=False):
        ''' walk the tree for ls based on names '''
        if self.verbose:
            Logger.info('walking path: \"{}\"'.format(path))
        r = anytree.resolver.Resolver('name')
        found = []
        try:
            found = r.glob(root, path)
            if len(found) < 1:
                return []
            if rec:
                self.print_tree(found[0].parent)
                return
            found = sorted(found, key=self._sort, reverse=self.sortsize)
            self._print_node(found[0].parent,
                             withpath=False, withdepth=True)
            for f in found:
                self._print_node(f, withpath=False, pre='- ', withdepth=True)
        except anytree.resolver.ChildResolverError:
            pass
        return found

    ###############################################################
    # tree creationg
    ###############################################################
    def _add_entry(self, name, top, resolv):
        ''' add an entry to the tree '''
        entries = name.rstrip(os.sep).split(os.sep)
        if len(entries) == 1:
            self.archive_node(name, name, top, top.name)
            return
        sub = os.sep.join(entries[:-1])
        f = entries[-1]
        try:
            parent = resolv.get(top, sub)
            parent = self.archive_node(f, name, parent, top.name)
        except anytree.resolver.ChildResolverError:
            self.archive_node(f, name, top, top.name)

    def list_to_tree(self, parent, names):
        ''' convert list of files to a tree '''
        if not names:
            return
        r = anytree.resolver.Resolver('name')
        for name in names:
            name = name.rstrip(os.sep)
            self._add_entry(name, parent, r)

    ###############################################################
    # diverse
    ###############################################################
    def _sort_tree(self, items):
        ''' sorting a list of items '''
        return sorted(items, key=self._sort, reverse=self.sortsize)

    def _sort(self, x):
        if self.sortsize:
            return self._sort_size(x)
        return self._sort_fs(x)

    def _sort_fs(self, n):
        ''' sorting nodes dir first and alpha '''
        return (n.type, n.name.lstrip('\.').lower())

    def _sort_size(self, n):
        ''' sorting nodes by size '''
        try:
            if not n.size:
                return 0
            return n.size
        except AttributeError:
            return 0

    def to_dot(self, node, path='tree.dot'):
        ''' export to dot for graphing '''
        anytree.exporter.DotExporter(node).to_dotfile(path)
        Logger.info('dot file created under \"{}\"'.format(path))
        return 'dot {} -T png -o /tmp/tree.png'.format(path)

    def _get_storage(self, node):
        ''' recursively traverse up to find storage '''
        return node.ancestors[1]

    def get_meta_node(self, top):
        ''' return the meta node if any '''
        try:
            return next(filter(lambda x: x.type == self.TYPE_META,
                        top.children))
        except StopIteration:
            return None

    def rec_size(self, node):
        ''' recursively traverse tree and store dir size '''
        if self.verbose:
            Logger.info('getting folder size recursively')
        if node.type == self.TYPE_FILE:
            return node.size
        size = 0
        for i in node.children:
            if node.type == self.TYPE_DIR:
                size += self.rec_size(i)
            if node.type == self.TYPE_STORAGE:
                self.rec_size(i)
            else:
                continue
        node.size = size
        return size
