
#
# rpclib - Copyright (C) Rpclib contributors.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301
#


"""This module contains the InterfaceBase class and its helper objects."""


import logging
logger = logging.getLogger(__name__)

import warnings
from rpclib.util.odict import odict

import rpclib.const.xml_ns
_ns_xsd = rpclib.const.xml_ns.xsd

from rpclib import EventManager
from rpclib.const.suffix import TYPE_SUFFIX
from rpclib.const.suffix import RESULT_SUFFIX
from rpclib.const.suffix import RESPONSE_SUFFIX

class SchemaInfo(object):
    def __init__(self):
        self.elements = odict()
        self.types = odict()

class Interface(object):
    """The base class for all interface document generators."""

    def __init__(self, app=None):
        self.__ns_counter = 0

        self.service_method_map = {}
        self.url = None
        self.event_manager = EventManager(self)

        self.__app = None
        self.set_app(app)

    def set_app(self, value):
        assert self.__app is None, "One interface instance should belong to one " \
                                   "application instance."

        self.__app = value
        self.populate_interface()

    @property
    def app(self):
        return self.__app

    @property
    def services(self):
        if self.__app:
            return self.__app.services
        return []

    def reset_interface(self):
        self.namespaces = odict()
        self.classes = {}
        self.imports = {}

        self.nsmap = dict(rpclib.const.xml_ns.const_nsmap)
        self.prefmap = dict(rpclib.const.xml_ns.const_prefmap)

        self.nsmap['tns'] = self.get_tns()
        self.prefmap[self.get_tns()] = 'tns'

    def has_class(self, cls):
        """Returns true if the given class is already included in the interface
        object somewhere."""

        ns_prefix = cls.get_namespace_prefix(self)
        type_name = cls.get_type_name()
        return ((ns_prefix in self.namespaces) and
                           (type_name in self.namespaces[ns_prefix].types))

    def get_schema_info(self, prefix):
        """Returns the SchemaInfo object for the corresponding namespace. It
        creates it if it doesn't exist.

        The SchemaInfo object holds the simple and complex type definitions
        for a given namespace."""

        if prefix in self.namespaces:
            schema = self.namespaces[prefix]
        else:
            schema = self.namespaces[prefix] = SchemaInfo()

        return schema

    def get_class(self, key):
        """Returns the class definition that corresponds to the given key.
        Keys are in '{namespace}class_name' form, a.k.a. XML QName format.

        Not meant to be overridden.
        """
        return self.classes[key]

    def get_class_instance(self, key):
        """Returns the default class instance that corresponds to the given key.
        Keys are in '{namespace}class_name' form, a.k.a. XML QName format.
        Classes should not enforce arguments to the constructor.

        Not meant to be overridden.
        """
        return self.classes[key]()

    def get_name(self):
        """Returns service name that is seen in the name attribute of the
        definitions tag.

        Not meant to be overridden.
        """

        if self.app:
            return self.app.name

    def get_tns(self):
        """Returns default namespace that is seen in the targetNamespace
        attribute of the definitions tag.

        Not meant to be overridden.
        """
        if self.app:
            return self.app.tns

    def __test_type_name_validity(self, c):
        if c and  ( c.get_type_name().endswith(RESULT_SUFFIX) or
                    c.get_type_name().endswith(RESPONSE_SUFFIX) ):
                raise Exception("You can't use any type or method name ending "
                                "with one of %r unless you should alter the "
                                "constants in the 'rpclib.const.suffix' module.\n"
                                "This is for class %r."
                            % ((TYPE_SUFFIX, RESULT_SUFFIX, RESPONSE_SUFFIX),c))

    def populate_interface(self, types=None):
        """Harvests the information stored in individual classes' _type_info
        dictionaries. It starts from function definitions and includes only
        the used objects.
        """

        self.reset_interface()

        classes = []
        # populate types
        for s in self.services:
            logger.debug("populating '%s.%s (%s) ' types..." % (s.__module__,
                                                s.__name__, s.get_service_key()))

            for method in s.public_methods.values():

                if method.in_header is None:
                    method.in_header = s.__in_header__
                if method.out_header is None:
                    method.out_header = s.__out_header__

                if not (method.in_header is None):
                    if isinstance(method.in_header, (list, tuple)):
                        in_headers = method.in_header
                    else:
                        in_headers = (method.in_header,)
                    for in_header in in_headers:
                        self.__test_type_name_validity(in_header)
                        in_header.resolve_namespace(in_header, self.get_tns())
                        classes.append(in_header)

                if not (method.out_header is None):
                    if isinstance(method.out_header, (list, tuple)):
                        out_headers = method.out_header
                    else:
                        out_headers = (method.out_header,)

                    for out_header in out_headers:
                        self.__test_type_name_validity(out_header)
                        out_header.resolve_namespace(out_header, self.get_tns())
                        classes.append(out_header)

                if method.faults is None:
                    method.faults = []
                elif not (isinstance(method.faults, (list, tuple))):
                    method.faults = (method.faults,)

                for fault in method.faults:
                    fault.__namespace__ = self.get_tns()
                    classes.append(fault)

                self.__test_type_name_validity(method.in_message)
                method.in_message.resolve_namespace(method.in_message,
                                                                 self.get_tns())
                classes.append(method.in_message)

                # we are not testing out_message with __test_type_name_validity
                # because they have RESPONSE_SUFFIX and RESULT_SUFFIX added
                # automatically. actually, they're what we're trying to protect.
                method.out_message.resolve_namespace(method.out_message,
                                                                 self.get_tns())
                classes.append(method.out_message)

        for c in classes:
            self.add(c)

        # populate call routes
        for s in self.services:
            s.__tns__ = self.get_tns()
            logger.debug("populating '%s.%s' methods..." % (s.__module__, s.__name__))
            for method in s.public_methods.values():
                val = self.service_method_map.get(method.key, None)
                if val is None:
                    logger.debug('\tadding method %r to match %r tag.' %
                                                      (method.name, method.key))
                    self.service_method_map[method.key] = [(s, method)]

                else:
                    if self.app.supports_fanout_methods:
                        self.service_method_map[method.key].append( (s, method) )

                    else:
                        os, om = val[0]
                        raise ValueError("\nThe message %r defined in both '%s.%s'"
                                                                " and '%s.%s'"
                                % (method.key, s.__module__, s.__name__,
                                               os.__module__, os.__name__,
                                ))

        logger.debug("From this point on, you're not supposed to make any changes "
                    "to the class & method structure of the exposed services.")

    tns = property(get_tns)

    def get_namespace_prefix(self, ns):
        """Returns the namespace prefix for the given namespace. Creates a new
        one automatically if it doesn't exist.

        Not meant to be overridden.
        """

        if not (isinstance(ns, str) or isinstance(ns, unicode)):
            raise TypeError(ns)

        if ns == "__main__":
            warnings.warn("Namespace is '__main__'", Warning )

        if not (ns in self.prefmap):
            pref = "s%d" % self.__ns_counter
            while pref in self.nsmap:
                self.__ns_counter += 1
                pref = "s%d" % self.__ns_counter

            self.prefmap[ns] = pref
            self.nsmap[pref] = ns

            self.__ns_counter += 1

        else:
            pref = self.prefmap[ns]

        return pref

    def add(self, cls):
        """This function is called by the populate_interface logic, which
        expects you to implement a way to manage incoming classes.

        In normal circumstances, the incoming classes are all ComplexModel
        children.
        """

        raise NotImplementedError('Extend and override.')

    def build_interface_document(self, cls):
        """This function is supposed to be called just once, as late as possible
        into the process start. It builds the interface document and caches it
        somewhere. The overriding function should never call the overridden
        function as this may result in the same event firing more than once.
        """

        raise NotImplementedError('Extend and override.')


    def get_interface_document(self, cls):
        """This function is called by server transports that try to satisfy the
        request for the interface document. This should just return a previously
        cached interface document.
        """

        raise NotImplementedError('Extend and override.')

    def add_simple_type(self, cls, node):
        ns = cls.get_namespace()
        tn = cls.get_type_name()
        pref = cls.get_namespace_prefix(self)

        self.__check_imports(cls, node)
        schema_info = self.get_schema_info(pref)
        schema_info.types[tn] = node

        class_key = '{%s}%s' % (ns, tn)
        logger.debug('\tadding class %r for %r' % (repr(cls), class_key))

        self.classes[class_key] = cls
        if ns == self.get_tns():
            self.classes[tn] = cls

    def add_complex_type(self, cls, node):
        ns = cls.get_namespace()
        tn = cls.get_type_name()
        pref = cls.get_namespace_prefix(self)

        self.__check_imports(cls, node)
        schema_info = self.get_schema_info(pref)
        schema_info.types[tn] = node

        class_key = '{%s}%s' % (ns, tn)
        logger.debug('\tadding class %r for %r' % (repr(cls), class_key))

        self.classes[class_key] = cls
        if ns == self.get_tns():
            self.classes[tn] = cls

    def is_valid_import(self, ns):
        return True

    def do_imports(self, cls):
        own_namespace = cls.get_namespace()

        if not (own_namespace in self.imports):
            self.imports[own_namespace] = set()

        for v in cls._type_info.values():
            ns = v.get_namespace()

            if ns != own_namespace and self.is_valid_import(ns):
                self.imports[own_namespace].add(ns)
