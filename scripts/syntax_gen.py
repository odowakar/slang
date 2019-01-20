#!/usr/bin/env python
# This script generates C++ source for parse tree syntax nodes from a data
# file.
import argparse
import os

class TypeInfo:
    def __init__(self, processedMembers, members, pointerMembers, optionalMembers,
                 final, constructorArgs, base, combinedMembers, notNullMembers):
        self.processedMembers = processedMembers
        self.members = members
        self.pointerMembers = pointerMembers
        self.optionalMembers = optionalMembers
        self.final = final
        self.constructorArgs = constructorArgs
        self.base = base
        self.combinedMembers = combinedMembers
        self.notNullMembers = notNullMembers

def main():
    parser = argparse.ArgumentParser(description='Diagnostic source generator')
    parser.add_argument('--dir', default=os.getcwd(), help='Output directory')
    args = parser.parse_args()

    ourdir = os.path.dirname(os.path.realpath(__file__))
    inf = open(os.path.join(ourdir, "syntax.txt"))

    headerdir = os.path.join(args.dir, 'slang', 'syntax')
    try:
        os.makedirs(headerdir)
    except OSError:
        pass

    outf = open(os.path.join(headerdir, "AllSyntax.h"), 'w')
    cppf = open(os.path.join(args.dir, "AllSyntax.cpp"), 'w')

    outf.write('''//------------------------------------------------------------------------------
// AllSyntax.h
// All generated syntax node data structures.
//
// File is under the MIT license; see LICENSE for details.
//------------------------------------------------------------------------------
#pragma once

#include "slang/parsing/Token.h"
#include "slang/syntax/SyntaxNode.h"
#include "slang/util/BumpAllocator.h"

// This file contains all parse tree syntax nodes.
// It is auto-generated by the syntax_gen.py script under the scripts/ directory.

namespace slang {

''')

    cppf.write('''//------------------------------------------------------------------------------
// AllSyntax.cpp
// All generated syntax node data structures.
//
// File is under the MIT license; see LICENSE for details.
//------------------------------------------------------------------------------
#include "slang/syntax/AllSyntax.h"

// This file contains all parse tree syntax node generated definitions.
// It is auto-generated by the syntax_gen.py script under the scripts/ directory.

namespace slang {

''')

    currtype = None
    currkind = None
    currtype_name = None
    tags = None
    alltypes = {}
    kindmap = {}

    alltypes['SyntaxNode'] = TypeInfo(None, None, None, None, '', None, None, [], None)

    for line in [x.strip('\n') for x in inf]:
        if line.startswith('//'):
            outf.write(line)
            outf.write('\n\n')
        elif len(line) == 0 or (currtype is not None and line == 'empty'):
            if currtype is not None:
                generate(outf, currtype_name, tags, currtype, alltypes, kindmap)
            currtype = None
            currkind = None
        elif currtype is not None:
            p = line.split(' ')
            if len(p) != 2:
                raise Exception("Two elements per member please.")
            currtype.append(p)
        elif currkind is not None:
            for k in line.split(' '):
                if k in kindmap:
                    raise Exception("More than one kind map for {}".format(k))
                kindmap[k] = currkind
        elif line.startswith('forward '):
            outf.write('struct {};\n'.format(line[8:]))
        elif line.startswith('kindmap<'):
            currkind = line[8:line.index('>')] + 'Syntax'
        else:
            p = line.split(' ')
            currtype_name = p[0] + 'Syntax'
            tags = p[1:] if len(p) > 1 else None
            currtype = []

    if currtype:
        generate(outf, currtype_name, tags, currtype, alltypes, kindmap)

    cppf.write('uint32_t SyntaxNode::getChildCount() const {\n')
    cppf.write('    switch (kind) {\n')
    cppf.write('        case SyntaxKind::Unknown: return 0;\n')
    cppf.write('        case SyntaxKind::SyntaxList:\n')
    cppf.write('        case SyntaxKind::TokenList:\n')
    cppf.write('        case SyntaxKind::SeparatedList:\n')
    cppf.write('            return ((const SyntaxListBase*)this)->getChildCount();\n')

    for k,v in sorted(kindmap.items()):
        count = len(alltypes[v].combinedMembers)
        cppf.write('        case SyntaxKind::{}: return {};\n'.format(k, count))

    cppf.write('    }\n')
    cppf.write('    THROW_UNREACHABLE;\n')
    cppf.write('}\n\n')

    reverseKindmap = {}
    for k,v in kindmap.items():
        if v in reverseKindmap:
            reverseKindmap[v].append(k)
        else:
            reverseKindmap[v] = [k]

    for k,v in alltypes.items():
        if not v.final:
            continue

        while v.base != 'SyntaxNode':
            kinds = reverseKindmap[k]
            if v.base in reverseKindmap:
                reverseKindmap[v.base].extend(kinds)
            else:
                reverseKindmap[v.base] = kinds[:]
            k = v.base
            v = alltypes[k]

    # Write out isKind static methods for each derived type
    for k,v in sorted(alltypes.items()):
        if v.base is None:
            continue

        cppf.write('bool {}::isKind(SyntaxKind kind) {{\n'.format(k))
        kinds = set(reverseKindmap[k])
        if len(kinds) == 1:
            cppf.write('    return kind == SyntaxKind::{};\n'.format(list(kinds)[0]))
        else:
            cppf.write('    switch (kind) {\n')
            for kind in sorted(kinds):
                cppf.write('        case SyntaxKind::{}:\n'.format(kind))
            cppf.write('            return true;\n')
            cppf.write('        default:\n')
            cppf.write('            return false;\n')
            cppf.write('    }\n')

        cppf.write('}\n\n')

        if len(v.members) != 0 or v.final != '':
            for returnType in ('TokenOrSyntax', 'ConstTokenOrSyntax'):
                cppf.write('{} {}::getChild(uint32_t index){} {{\n'.format(returnType, k, '' if returnType == 'TokenOrSyntax' else ' const'))

                if len(v.combinedMembers) > 0:
                    cppf.write('    switch (index) {\n')

                    index = 0
                    for m in v.combinedMembers:
                        addr = '&' if m[1] in v.pointerMembers else ''
                        get = '.get()' if m[1] in v.notNullMembers else ''
                        cppf.write('        case {}: return {}{}{};\n'.format(index, addr, m[1], get))
                        index += 1

                    cppf.write('        default: return nullptr;\n')
                    cppf.write('    }\n')
                else:
                    cppf.write('    (void)index;\n')
                    cppf.write('    return nullptr;\n')

                cppf.write('}\n\n')

            cppf.write('void {}::setChild(uint32_t index, TokenOrSyntax child) {{\n'.format(k))
            if len(v.combinedMembers) > 0:
                cppf.write('    switch (index) {\n')

                index = 0
                for m in v.combinedMembers:
                    cppf.write('        case {}: '.format(index))
                    index += 1

                    if m[0] == 'token':
                        cppf.write('{} = child.token(); return;\n'.format(m[1]))
                    elif m[1] in v.pointerMembers:
                        cppf.write('{} = child.node()->as<{}>(); return;\n'.format(m[1], m[0]))
                    else:
                        cppf.write('{} = &child.node()->as<{}>(); return;\n'.format(m[1], m[0]))

                cppf.write('        default: THROW_UNREACHABLE;\n')
                cppf.write('    }\n')
            else:
                cppf.write('    (void)index;\n')
                cppf.write('    (void)child;\n')

            cppf.write('}\n\n')

            cppf.write('{0}* {0}::clone(BumpAllocator& alloc) const {{\n'.format(k))
            cppf.write('    return alloc.emplace<{}>(*this);\n'.format(k))
            cppf.write('}\n\n')

    # Write out syntax factory methods
    outf.write('class SyntaxFactory {\n')
    outf.write('public:\n')
    outf.write('    explicit SyntaxFactory(BumpAllocator& alloc) : alloc(alloc) {}\n')
    outf.write('\n')

    for k,v in sorted(alltypes.items()):
        if not v.final:
            continue

        methodName = k
        if methodName.endswith('Syntax'):
            methodName = methodName[:-6]
        methodName = methodName[:1].lower() + methodName[1:]
        outf.write('    {}& {}({});\n'.format(k, methodName, v.constructorArgs))

        argNames = ' '.join(v.constructorArgs.split(' ')[1::2])
        cppf.write('{}& SyntaxFactory::{}({}) {{\n'.format(k, methodName, v.constructorArgs))
        cppf.write('    return *alloc.emplace<{}>({});\n'.format(k, argNames))
        cppf.write('}\n\n')

    outf.write('\n')
    outf.write('private:\n')
    outf.write('    BumpAllocator& alloc;\n')
    outf.write('};\n\n')

    # Write out a dispatch method to get from SyntaxKind to actual concrete type
    outf.write('namespace detail {\n\n')
    outf.write('template<typename TNode, typename TVisitor, typename... Args>\n')
    outf.write('decltype(auto) visitSyntaxNode(TNode* node, TVisitor& visitor, Args&&... args) {\n')
    outf.write('    static constexpr bool isConst = std::is_const_v<TNode>;')
    outf.write('    switch (node->kind) {\n')
    outf.write('        case SyntaxKind::Unknown: return visitor.visitInvalid(*node, std::forward<Args>(args)...);\n')
    outf.write('        case SyntaxKind::SyntaxList:\n')
    outf.write('        case SyntaxKind::TokenList:\n')
    outf.write('        case SyntaxKind::SeparatedList:\n')
    outf.write('            return visitor.visit(*static_cast<std::conditional_t<isConst, const SyntaxListBase*, SyntaxListBase*>>(node), std::forward<Args>(args)...);\n')

    for k,v in sorted(kindmap.items()):
        outf.write('        case SyntaxKind::{}: return visitor.visit(*static_cast<'.format(k))
        outf.write('std::conditional_t<isConst, const {0}*, {0}*>>(node), std::forward<Args>(args)...);\n'.format(v))
        alltypes.pop(v, None)

    outf.write('    }\n')
    outf.write('    THROW_UNREACHABLE;\n')
    outf.write('}\n\n')
    outf.write('}\n\n')

    outf.write('template<typename TVisitor, typename... Args>\n')
    outf.write('decltype(auto) SyntaxNode::visit(TVisitor& visitor, Args&&... args) {\n')
    outf.write('    return detail::visitSyntaxNode(this, visitor, std::forward<Args>(args)...);\n')
    outf.write('}\n\n')

    outf.write('template<typename TVisitor, typename... Args>\n')
    outf.write('decltype(auto) SyntaxNode::visit(TVisitor& visitor, Args&&... args) const {\n')
    outf.write('    return detail::visitSyntaxNode(this, visitor, std::forward<Args>(args)...);\n')
    outf.write('}\n\n')

    outf.write('}\n')
    cppf.write('}\n')

    # Do some checking to make sure all types have at least one kind assigned,
    # or has set final=false.  We already removed types from alltypes in the
    # loop above.
    for k,v in alltypes.items():
        if v.final:
            print("Type '{}' has no kinds assigned to it.".format(k))

def generate(outf, name, tags, members, alltypes, kindmap):
    tagdict = {}
    if tags:
        for t in tags:
            p = t.split('=')
            tagdict[p[0]] = p[1]

    base = tagdict['base'] + 'Syntax' if 'base' in tagdict else 'SyntaxNode'
    outf.write('struct {} : public {} {{\n'.format(name, base))

    pointerMembers = set()
    optionalMembers = set()
    notNullMembers = set()
    processed_members = []
    baseInitializers = ''
    combined = members
    if base != 'SyntaxNode':
        processed_members.extend(alltypes[base].processedMembers)
        pointerMembers = pointerMembers.union(alltypes[base].pointerMembers)
        optionalMembers = optionalMembers.union(alltypes[base].optionalMembers)
        notNullMembers = notNullMembers.union(alltypes[base].notNullMembers)
        baseInitializers = ', '.join([x[1] for x in alltypes[base].members])
        if baseInitializers:
            baseInitializers = ', ' + baseInitializers
        combined = alltypes[base].members + members

    for m in members:
        membertype = None
        if m[0] == 'token':
            typename = 'Token'
        elif m[0] == 'tokenlist':
            m[0] = typename = 'TokenList'
            pointerMembers.add(m[1])
        elif m[0].startswith('list<'):
            last = m[0][5:m[0].index('>')]
            if not last.endswith('SyntaxNode'):
                last += 'Syntax'

            m[0] = typename = 'SyntaxList<' + last + '>'
            pointerMembers.add(m[1])
        elif m[0].startswith('separated_list<'):
            last = m[0][15:m[0].index('>')]
            if not last.endswith('SyntaxNode'):
                last += 'Syntax'

            m[0] = typename = 'SeparatedSyntaxList<' + last + '>'
            pointerMembers.add(m[1])
        else:
            optional = False
            if m[0].endswith('?'):
                optional = True
                m[0] = m[0][:-1]

            if m[0] != 'SyntaxNode':
                m[0] += 'Syntax'

            if m[0] not in alltypes:
                raise Exception("Unknown type '{}'".format(m[0]))

            if optional:
                typename = m[0] + '*'
                optionalMembers.add(m[1])
            else:
                notNullMembers.add(m[1])
                typename = m[0] + '&'
                membertype = 'not_null<{}*>'.format(m[0])

        l = '{} {}'.format(typename, m[1])
        processed_members.append(l)

        if membertype is None:
            outf.write('    {};\n'.format(l))
        else:
            outf.write('    {} {};\n'.format(membertype, m[1]))

    kindArg = 'SyntaxKind kind' if 'kind' not in tagdict else ''
    kindValue = 'kind' if 'kind' not in tagdict else 'SyntaxKind::' + tagdict['kind']

    if 'kind' in tagdict:
        k = tagdict['kind']
        if k in kindmap:
            raise Exception("More than one kind map for {}".format(k))
        kindmap[k] = name

    if kindArg and len(processed_members) > 0:
        kindArg += ', '

    initializers = ', '.join(['{0}({1}{0})'.format(x[1], '&' if x[1] in notNullMembers else '') for x in members])
    if initializers:
        initializers = ', ' + initializers

    final = ' final'
    if 'final' in tagdict and tagdict['final'] == 'false':
        final = ''

    constructorArgs = '{}{}'.format(kindArg, ', '.join(processed_members))
    alltypes[name] = TypeInfo(processed_members, members, pointerMembers, optionalMembers,
                              final, constructorArgs, base, combined, notNullMembers)

    outf.write('\n')
    outf.write('    {}({}) :\n'.format(name, constructorArgs))
    outf.write('        {}({}{}){} {{\n'.format(base, kindValue, baseInitializers, initializers))

    for m in members:
        if m[0] == 'token':
            continue
        if m[1] in pointerMembers:
            outf.write('        this->{}.parent = this;\n'.format(m[1]))
            if m[0].startswith('SyntaxList<') or m[0].startswith('SeparatedSyntaxList<'):
                outf.write('        for (auto child : this->{})\n'.format(m[1]))
                outf.write('            child->parent = this;\n')

        elif m[1] in optionalMembers:
            outf.write('        if (this->{0}) this->{0}->parent = this;\n'.format(m[1]))
        else:
            outf.write('        this->{}->parent = this;\n'.format(m[1]))

    outf.write('    }\n\n')

    if len(members) == 0 and final == '':
        outf.write('    static bool isKind(SyntaxKind kind);\n')
    else:
        outf.write('    static bool isKind(SyntaxKind kind);\n\n')

        outf.write('    TokenOrSyntax getChild(uint32_t index);\n')
        outf.write('    ConstTokenOrSyntax getChild(uint32_t index) const;\n')
        outf.write('    void setChild(uint32_t index, TokenOrSyntax child);\n\n')
        outf.write('    {}* clone(BumpAllocator& alloc) const;\n'.format(name))

    outf.write('};\n\n')

if __name__ == "__main__":
    main()
