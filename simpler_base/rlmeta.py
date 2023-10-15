SUPPORT = 'import contextlib\nimport sys\n\nclass Or:\n    def __init__(self, matchers):\n        self.matchers = matchers\n    def run(self, stream):\n        for matcher in self.matchers:\n            state = stream.save()\n            try:\n                return matcher.run(stream)\n            except ParseError:\n                stream.restore(state)\n        stream.error("no or match")\n\nclass Scope:\n    def __init__(self, matcher):\n        self.matcher = matcher\n    def run(self, stream):\n        stream.push_scope()\n        result = self.matcher.run(stream)\n        stream.pop_scope()\n        return result\n\nclass Not:\n    def __init__(self, matcher):\n        self.matcher = matcher\n    def run(self, stream):\n        with stream.in_not():\n            state = stream.save()\n            try:\n                self.matcher.run(stream)\n            except ParseError:\n                return stream.action(lambda self: None)\n            finally:\n                stream.restore(state)\n        stream.error("not matched")\n\nclass And:\n    def __init__(self, matchers):\n        self.matchers = matchers\n    def run(self, stream):\n        result = stream.action(lambda self: None)\n        for matcher in self.matchers:\n            result = matcher.run(stream)\n        return result\n\nclass MatchList:\n    def __init__(self, matcher):\n        self.matcher = matcher\n    def run(self, stream):\n        return stream.match_list(self.matcher)\n\nclass MatchCallRule:\n    def __init__(self, namespace):\n        self.namespace = namespace\n    def run(self, stream):\n        return stream.match_call_rule(self.namespace)\n\nclass Bind:\n    def __init__(self, name, value):\n        self.name = name\n        self.value = value\n    def run(self, stream):\n        return stream.bind(self.name, self.value.run(stream))\n\nclass MatchObject:\n    def __init__(self, fn, description):\n        self.fn = fn\n        self.description = description\n    def run(self, stream):\n        return stream.match(self.fn, self.description)\n\nclass MatchRule:\n    def __init__(self, name):\n        self.name = name\n    def run(self, stream):\n        return rules[self.name].run(stream)\n\nclass Star:\n    def __init__(self, matcher):\n        self.matcher = matcher\n    def run(self, stream):\n        results = []\n        while True:\n            state = stream.save()\n            try:\n                results.append(self.matcher.run(stream))\n            except ParseError:\n                stream.restore(state)\n                break\n        return stream.action(lambda self: [x.eval(self.runtime) for x in results])\n\nclass Action:\n    def __init__(self, fn):\n        self.fn = fn\n    def run(self, stream):\n        return stream.action(self.fn)\n\nclass RuntimeAction:\n    def __init__(self, scope, fn):\n        self.scope = scope\n        self.fn = fn\n    def eval(self, runtime):\n        self.runtime = runtime\n        return self.fn(self)\n    def bind(self, name, value, continuation):\n        self.runtime.bind(name, value)\n        return continuation()\n    def lookup(self, name):\n        if name in self.scope:\n            return self.scope[name].eval(self.runtime)\n        else:\n            return self.runtime.lookup(name)\n\ndef splice(depth, item):\n    if depth == 0:\n        return [item]\n    else:\n        return concat([splice(depth-1, subitem) for subitem in item])\n\ndef concat(lists):\n    return [x for xs in lists for x in xs]\n\ndef join(items, delimiter=""):\n    return delimiter.join(\n        join(item, delimiter) if isinstance(item, list) else str(item)\n        for item in items\n    )\n\nclass Stream:\n    def __init__(self, items):\n        self.items = items\n        self.scopes = []\n        self.index = 0\n        self.latest_error = None\n        self.skip_record = False\n    def action(self, fn):\n        return RuntimeAction(self.scopes[-1], fn)\n    @contextlib.contextmanager\n    def in_not(self):\n        prev = self.skip_record\n        try:\n            self.skip_record = True\n            yield\n        finally:\n            self.skip_record = prev\n    def save(self):\n        return (self.items, [dict(x) for x in self.scopes], self.index)\n    def restore(self, values):\n        (self.items, self.scopes, self.index) = values\n    def push_scope(self):\n        self.scopes.append({})\n    def pop_scope(self):\n        return self.scopes.pop(-1)\n    def bind(self, name, value):\n        self.scopes[-1][name] = value\n        return value\n    def match_list(self, matcher):\n        if self.index < len(self.items):\n            items, index = self.items, self.index\n            self.items = self.items[self.index]\n            self.index = 0\n            try:\n                result = matcher.run(self)\n            finally:\n                self.items, self.index = items, index\n                self.index += 1\n            return result\n        self.error("no list found")\n    def match_call_rule(self, namespace):\n        name = namespace + "." + self.items[self.index]\n        if name in rules:\n            rule = rules[name]\n            self.index += 1\n            return rule.run(self)\n        else:\n            self.error("unknown rule")\n    def match(self, fn, description):\n        if self.index < len(self.items):\n            object = self.items[self.index]\n            if self.index < len(self.items) and fn(object):\n                self.index += 1\n                return self.action(lambda self: object)\n        self.error(f"expected {description}")\n    def error(self, name):\n        if not self.skip_record and not self.latest_error or self.index > self.latest_error[2]:\n            self.latest_error = (name, self.items, self.index)\n        raise ParseError(*self.latest_error)\n\nclass ParseError(Exception):\n    def __init__(self, name, items, index):\n        Exception.__init__(self, name)\n        self.items = items\n        self.index = index\n        self.stream = items\n        self.pos = index\n        self.message = str(self)\n    def report(self):\n        print(self.items[:self.index] + "<ERR>" + self.items[self.index:])\n        print()\n        print("ERROR: " + str(self))\n\nclass Runtime:\n\n    def __init__(self):\n        self.vars = {\n            "len": len,\n            "label": Counter,\n            "indent": indent,\n            "join": join,\n            "repr": repr,\n            "indentprefix": "    ",\n        }\n\n    def bind(self, name, value):\n        self.vars[name] = value\n\n    def lookup(self, name):\n        return self.vars[name]\n\ndef indent(text, prefix="    "):\n    return "".join(prefix+line for line in text.splitlines(True))\n\nclass Counter(object):\n\n    def __init__(self):\n        self.value = 0\n\n    def __call__(self):\n        result = self.value\n        self.value += 1\n        return result\n\ndef compile_chain(grammars, source):\n    import os\n    import sys\n    import pprint\n    for rule in grammars:\n        try:\n            source = rules[rule].run(Stream(source)).eval(Runtime())\n        except ParseError as e:\n            marker = "<ERROR POSITION>"\n            if os.isatty(sys.stderr.fileno()):\n                marker = f"\\033[0;31m{marker}\\033[0m"\n            if isinstance(e.stream, str):\n                stream_string = e.stream[:e.pos] + marker + e.stream[e.pos:]\n            else:\n                stream_string = pprint.pformat(e.stream)\n            sys.exit("ERROR: {}\\nPOSITION: {}\\nSTREAM:\\n{}".format(\n                e.message,\n                e.pos,\n                indent(stream_string)\n            ))\n    return source\n\nrules = {}\n'
import contextlib
import sys

class Or:
    def __init__(self, matchers):
        self.matchers = matchers
    def run(self, stream):
        for matcher in self.matchers:
            state = stream.save()
            try:
                return matcher.run(stream)
            except ParseError:
                stream.restore(state)
        stream.error("no or match")

class Scope:
    def __init__(self, matcher):
        self.matcher = matcher
    def run(self, stream):
        stream.push_scope()
        result = self.matcher.run(stream)
        stream.pop_scope()
        return result

class Not:
    def __init__(self, matcher):
        self.matcher = matcher
    def run(self, stream):
        with stream.in_not():
            state = stream.save()
            try:
                self.matcher.run(stream)
            except ParseError:
                return stream.action(lambda self: None)
            finally:
                stream.restore(state)
        stream.error("not matched")

class And:
    def __init__(self, matchers):
        self.matchers = matchers
    def run(self, stream):
        result = stream.action(lambda self: None)
        for matcher in self.matchers:
            result = matcher.run(stream)
        return result

class MatchList:
    def __init__(self, matcher):
        self.matcher = matcher
    def run(self, stream):
        return stream.match_list(self.matcher)

class MatchCallRule:
    def __init__(self, namespace):
        self.namespace = namespace
    def run(self, stream):
        return stream.match_call_rule(self.namespace)

class Bind:
    def __init__(self, name, value):
        self.name = name
        self.value = value
    def run(self, stream):
        return stream.bind(self.name, self.value.run(stream))

class MatchObject:
    def __init__(self, fn, description):
        self.fn = fn
        self.description = description
    def run(self, stream):
        return stream.match(self.fn, self.description)

class MatchRule:
    def __init__(self, name):
        self.name = name
    def run(self, stream):
        return rules[self.name].run(stream)

class Star:
    def __init__(self, matcher):
        self.matcher = matcher
    def run(self, stream):
        results = []
        while True:
            state = stream.save()
            try:
                results.append(self.matcher.run(stream))
            except ParseError:
                stream.restore(state)
                break
        return stream.action(lambda self: [x.eval(self.runtime) for x in results])

class Action:
    def __init__(self, fn):
        self.fn = fn
    def run(self, stream):
        return stream.action(self.fn)

class RuntimeAction:
    def __init__(self, scope, fn):
        self.scope = scope
        self.fn = fn
    def eval(self, runtime):
        self.runtime = runtime
        return self.fn(self)
    def bind(self, name, value, continuation):
        self.runtime.bind(name, value)
        return continuation()
    def lookup(self, name):
        if name in self.scope:
            return self.scope[name].eval(self.runtime)
        else:
            return self.runtime.lookup(name)

def splice(depth, item):
    if depth == 0:
        return [item]
    else:
        return concat([splice(depth-1, subitem) for subitem in item])

def concat(lists):
    return [x for xs in lists for x in xs]

def join(items, delimiter=""):
    return delimiter.join(
        join(item, delimiter) if isinstance(item, list) else str(item)
        for item in items
    )

class Stream:
    def __init__(self, items):
        self.items = items
        self.scopes = []
        self.index = 0
        self.latest_error = None
        self.skip_record = False
    def action(self, fn):
        return RuntimeAction(self.scopes[-1], fn)
    @contextlib.contextmanager
    def in_not(self):
        prev = self.skip_record
        try:
            self.skip_record = True
            yield
        finally:
            self.skip_record = prev
    def save(self):
        return (self.items, [dict(x) for x in self.scopes], self.index)
    def restore(self, values):
        (self.items, self.scopes, self.index) = values
    def push_scope(self):
        self.scopes.append({})
    def pop_scope(self):
        return self.scopes.pop(-1)
    def bind(self, name, value):
        self.scopes[-1][name] = value
        return value
    def match_list(self, matcher):
        if self.index < len(self.items):
            items, index = self.items, self.index
            self.items = self.items[self.index]
            self.index = 0
            try:
                result = matcher.run(self)
            finally:
                self.items, self.index = items, index
                self.index += 1
            return result
        self.error("no list found")
    def match_call_rule(self, namespace):
        name = namespace + "." + self.items[self.index]
        if name in rules:
            rule = rules[name]
            self.index += 1
            return rule.run(self)
        else:
            self.error("unknown rule")
    def match(self, fn, description):
        if self.index < len(self.items):
            object = self.items[self.index]
            if self.index < len(self.items) and fn(object):
                self.index += 1
                return self.action(lambda self: object)
        self.error(f"expected {description}")
    def error(self, name):
        if not self.skip_record and not self.latest_error or self.index > self.latest_error[2]:
            self.latest_error = (name, self.items, self.index)
        raise ParseError(*self.latest_error)

class ParseError(Exception):
    def __init__(self, name, items, index):
        Exception.__init__(self, name)
        self.items = items
        self.index = index
        self.stream = items
        self.pos = index
        self.message = str(self)
    def report(self):
        print(self.items[:self.index] + "<ERR>" + self.items[self.index:])
        print()
        print("ERROR: " + str(self))

class Runtime:

    def __init__(self):
        self.vars = {
            "len": len,
            "label": Counter,
            "indent": indent,
            "join": join,
            "repr": repr,
            "indentprefix": "    ",
        }

    def bind(self, name, value):
        self.vars[name] = value

    def lookup(self, name):
        return self.vars[name]

def indent(text, prefix="    "):
    return "".join(prefix+line for line in text.splitlines(True))

class Counter(object):

    def __init__(self):
        self.value = 0

    def __call__(self):
        result = self.value
        self.value += 1
        return result

def compile_chain(grammars, source):
    import os
    import sys
    import pprint
    for rule in grammars:
        try:
            source = rules[rule].run(Stream(source)).eval(Runtime())
        except ParseError as e:
            marker = "<ERROR POSITION>"
            if os.isatty(sys.stderr.fileno()):
                marker = f"\033[0;31m{marker}\033[0m"
            if isinstance(e.stream, str):
                stream_string = e.stream[:e.pos] + marker + e.stream[e.pos:]
            else:
                stream_string = pprint.pformat(e.stream)
            sys.exit("ERROR: {}\nPOSITION: {}\nSTREAM:\n{}".format(
                e.message,
                e.pos,
                indent(stream_string)
            ))
    return source

rules = {}
rules['Parser.file'] = Or([
    Scope(And([
        Bind('xs', Star(Or([
            Scope(And([
                MatchRule('Parser.space'),
                MatchRule('Parser.namespace')]))]))),
        MatchRule('Parser.space'),
        Not(MatchObject(lambda x: True, 'True')),
        Action(lambda self: self.lookup('xs'))]))])
rules['Parser.namespace'] = Or([
    Scope(And([
        Bind('x', MatchRule('Parser.name')),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '{', "x == '{'")]),
        Bind('ys', Star(MatchRule('Parser.rule'))),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '}', "x == '}'")]),
        Action(lambda self: concat([
            splice(0, 'Namespace'),
            splice(0, self.lookup('x')),
            splice(1, self.lookup('ys'))]))]))])
rules['Parser.rule'] = Or([
    Scope(And([
        Bind('x', MatchRule('Parser.name')),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '=', "x == '='")]),
        Bind('y', MatchRule('Parser.choice')),
        Action(lambda self: concat([
            splice(0, 'Rule'),
            splice(0, self.lookup('x')),
            splice(0, self.lookup('y'))]))]))])
rules['Parser.choice'] = Or([
    Scope(And([
        Or([
            Or([
                Scope(And([
                    MatchRule('Parser.space'),
                    And([
                        MatchObject(lambda x: x == '|', "x == '|'")])]))]),
            And([
            ])]),
        Bind('x', MatchRule('Parser.sequence')),
        Bind('xs', Star(Or([
            Scope(And([
                MatchRule('Parser.space'),
                And([
                    MatchObject(lambda x: x == '|', "x == '|'")]),
                MatchRule('Parser.sequence')]))]))),
        Action(lambda self: concat([
            splice(0, 'Or'),
            splice(0, self.lookup('x')),
            splice(1, self.lookup('xs'))]))]))])
rules['Parser.sequence'] = Or([
    Scope(And([
        Bind('xs', Star(MatchRule('Parser.expr'))),
        Bind('ys', MatchRule('Parser.maybeAction')),
        Action(lambda self: concat([
            splice(0, 'Scope'),
            splice(0, concat([
                splice(0, 'And'),
                splice(1, self.lookup('xs')),
                splice(1, self.lookup('ys'))]))]))]))])
rules['Parser.expr'] = Or([
    Scope(And([
        Bind('x', MatchRule('Parser.expr1')),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == ':', "x == ':'")]),
        Bind('y', MatchRule('Parser.name')),
        Action(lambda self: concat([
            splice(0, 'Bind'),
            splice(0, self.lookup('y')),
            splice(0, self.lookup('x'))]))])),
    Scope(And([
        MatchRule('Parser.expr1')]))])
rules['Parser.expr1'] = Or([
    Scope(And([
        Bind('x', MatchRule('Parser.expr2')),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '*', "x == '*'")]),
        Action(lambda self: concat([
            splice(0, 'Star'),
            splice(0, self.lookup('x'))]))])),
    Scope(And([
        Bind('x', MatchRule('Parser.expr2')),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '?', "x == '?'")]),
        Action(lambda self: concat([
            splice(0, 'Or'),
            splice(0, self.lookup('x')),
            splice(0, concat([
                splice(0, 'And')]))]))])),
    Scope(And([
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '!', "x == '!'")]),
        Bind('x', MatchRule('Parser.expr2')),
        Action(lambda self: concat([
            splice(0, 'Not'),
            splice(0, self.lookup('x'))]))])),
    Scope(And([
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '%', "x == '%'")]),
        Action(lambda self: concat([
            splice(0, 'MatchCallRule')]))])),
    Scope(And([
        MatchRule('Parser.expr2')]))])
rules['Parser.expr2'] = Or([
    Scope(And([
        Bind('x', MatchRule('Parser.name')),
        Not(Or([
            Scope(And([
                MatchRule('Parser.space'),
                And([
                    MatchObject(lambda x: x == '=', "x == '='")])]))])),
        Action(lambda self: concat([
            splice(0, 'MatchRule'),
            splice(0, self.lookup('x'))]))])),
    Scope(And([
        MatchRule('Parser.space'),
        Bind('x', MatchRule('Parser.char')),
        And([
            MatchObject(lambda x: x == '-', "x == '-'")]),
        Bind('y', MatchRule('Parser.char')),
        Action(lambda self: concat([
            splice(0, 'MatchObject'),
            splice(0, concat([
                splice(0, 'Range'),
                splice(0, self.lookup('x')),
                splice(0, self.lookup('y'))]))]))])),
    Scope(And([
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == "'", 'x == "\'"')]),
        Bind('xs', Star(Or([
            Scope(And([
                Not(And([
                    MatchObject(lambda x: x == "'", 'x == "\'"')])),
                MatchRule('Parser.matchChar')]))]))),
        And([
            MatchObject(lambda x: x == "'", 'x == "\'"')]),
        Action(lambda self: concat([
            splice(0, 'And'),
            splice(1, self.lookup('xs'))]))])),
    Scope(And([
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '.', "x == '.'")]),
        Action(lambda self: concat([
            splice(0, 'MatchObject'),
            splice(0, concat([
                splice(0, 'Any')]))]))])),
    Scope(And([
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '(', "x == '('")]),
        Bind('x', MatchRule('Parser.choice')),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == ')', "x == ')'")]),
        Action(lambda self: self.lookup('x'))])),
    Scope(And([
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '[', "x == '['")]),
        Bind('xs', Star(MatchRule('Parser.expr'))),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == ']', "x == ']'")]),
        Action(lambda self: concat([
            splice(0, 'MatchList'),
            splice(0, concat([
                splice(0, 'And'),
                splice(1, self.lookup('xs'))]))]))]))])
rules['Parser.matchChar'] = Or([
    Scope(And([
        Bind('x', MatchRule('Parser.innerChar')),
        Action(lambda self: concat([
            splice(0, 'MatchObject'),
            splice(0, concat([
                splice(0, 'Eq'),
                splice(0, self.lookup('x'))]))]))]))])
rules['Parser.maybeAction'] = Or([
    Scope(And([
        Bind('x', MatchRule('Parser.actionExpr')),
        Action(lambda self: concat([
            splice(0, concat([
                splice(0, 'Action'),
                splice(0, self.lookup('x'))]))]))])),
    Scope(And([
        Action(lambda self: concat([
        ]))]))])
rules['Parser.actionExpr'] = Or([
    Scope(And([
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '-', "x == '-'"),
            MatchObject(lambda x: x == '>', "x == '>'")]),
        Bind('x', MatchRule('Parser.hostExpr')),
        Bind('y', Or([
            Scope(And([
                MatchRule('Parser.space'),
                And([
                    MatchObject(lambda x: x == ':', "x == ':'")]),
                MatchRule('Parser.name')])),
            Scope(And([
                Action(lambda self: '')]))])),
        Bind('z', MatchRule('Parser.actionExpr')),
        Action(lambda self: concat([
            splice(0, 'Set'),
            splice(0, self.lookup('y')),
            splice(0, self.lookup('x')),
            splice(0, self.lookup('z'))]))])),
    Scope(And([
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '-', "x == '-'"),
            MatchObject(lambda x: x == '>', "x == '>'")]),
        MatchRule('Parser.hostExpr')]))])
rules['Parser.hostExpr'] = Or([
    Scope(And([
        MatchRule('Parser.space'),
        Bind('x', MatchRule('Parser.string')),
        Action(lambda self: concat([
            splice(0, 'String'),
            splice(0, self.lookup('x'))]))])),
    Scope(And([
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '[', "x == '['")]),
        Bind('xs', Star(MatchRule('Parser.hostListItem'))),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == ']', "x == ']'")]),
        Action(lambda self: concat([
            splice(0, 'List'),
            splice(1, self.lookup('xs'))]))])),
    Scope(And([
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '{', "x == '{'")]),
        Bind('xs', Star(MatchRule('Parser.formatExpr'))),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '}', "x == '}'")]),
        Action(lambda self: concat([
            splice(0, 'Format'),
            splice(1, self.lookup('xs'))]))])),
    Scope(And([
        Bind('x', MatchRule('Parser.var')),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '(', "x == '('")]),
        Bind('ys', Star(MatchRule('Parser.hostExpr'))),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == ')', "x == ')'")]),
        Action(lambda self: concat([
            splice(0, 'Call'),
            splice(0, self.lookup('x')),
            splice(1, self.lookup('ys'))]))])),
    Scope(And([
        MatchRule('Parser.var')]))])
rules['Parser.hostListItem'] = Or([
    Scope(And([
        MatchRule('Parser.space'),
        Bind('ys', Star(And([
            MatchObject(lambda x: x == '~', "x == '~'")]))),
        Bind('x', MatchRule('Parser.hostExpr')),
        Action(lambda self: concat([
            splice(0, 'ListItem'),
            splice(0, self.lookup('len')(
                self.lookup('ys'))),
            splice(0, self.lookup('x'))]))]))])
rules['Parser.formatExpr'] = Or([
    Scope(And([
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '>', "x == '>'")]),
        Bind('xs', Star(MatchRule('Parser.formatExpr'))),
        MatchRule('Parser.space'),
        And([
            MatchObject(lambda x: x == '<', "x == '<'")]),
        Action(lambda self: concat([
            splice(0, 'Indent'),
            splice(0, concat([
                splice(0, 'Format'),
                splice(1, self.lookup('xs'))]))]))])),
    Scope(And([
        MatchRule('Parser.hostExpr')]))])
rules['Parser.var'] = Or([
    Scope(And([
        Bind('x', MatchRule('Parser.name')),
        Not(Or([
            Scope(And([
                MatchRule('Parser.space'),
                And([
                    MatchObject(lambda x: x == '=', "x == '='")])]))])),
        Action(lambda self: concat([
            splice(0, 'Lookup'),
            splice(0, self.lookup('x'))]))]))])
rules['Parser.string'] = Or([
    Scope(And([
        And([
            MatchObject(lambda x: x == '"', 'x == \'"\'')]),
        Bind('xs', Star(Or([
            Scope(And([
                Not(And([
                    MatchObject(lambda x: x == '"', 'x == \'"\'')])),
                MatchRule('Parser.innerChar')]))]))),
        And([
            MatchObject(lambda x: x == '"', 'x == \'"\'')]),
        Action(lambda self: join([
            self.lookup('xs')]))]))])
rules['Parser.char'] = Or([
    Scope(And([
        And([
            MatchObject(lambda x: x == "'", 'x == "\'"')]),
        Not(And([
            MatchObject(lambda x: x == "'", 'x == "\'"')])),
        Bind('x', MatchRule('Parser.innerChar')),
        And([
            MatchObject(lambda x: x == "'", 'x == "\'"')]),
        Action(lambda self: self.lookup('x'))]))])
rules['Parser.innerChar'] = Or([
    Scope(And([
        And([
            MatchObject(lambda x: x == '\\', "x == '\\\\'")]),
        MatchRule('Parser.escape')])),
    Scope(And([
        MatchObject(lambda x: True, 'True')]))])
rules['Parser.escape'] = Or([
    Scope(And([
        And([
            MatchObject(lambda x: x == '\\', "x == '\\\\'")]),
        Action(lambda self: '\\')])),
    Scope(And([
        And([
            MatchObject(lambda x: x == "'", 'x == "\'"')]),
        Action(lambda self: "'")])),
    Scope(And([
        And([
            MatchObject(lambda x: x == '"', 'x == \'"\'')]),
        Action(lambda self: '"')])),
    Scope(And([
        And([
            MatchObject(lambda x: x == 'n', "x == 'n'")]),
        Action(lambda self: '\n')]))])
rules['Parser.name'] = Or([
    Scope(And([
        MatchRule('Parser.space'),
        Bind('x', MatchRule('Parser.nameStart')),
        Bind('xs', Star(MatchRule('Parser.nameChar'))),
        Action(lambda self: join([
            self.lookup('x'),
            self.lookup('xs')]))]))])
rules['Parser.nameStart'] = Or([
    Scope(And([
        MatchObject(lambda x: 'a' <= x <= 'z', "'a' <= x <= 'z'")])),
    Scope(And([
        MatchObject(lambda x: 'A' <= x <= 'Z', "'A' <= x <= 'Z'")]))])
rules['Parser.nameChar'] = Or([
    Scope(And([
        MatchObject(lambda x: 'a' <= x <= 'z', "'a' <= x <= 'z'")])),
    Scope(And([
        MatchObject(lambda x: 'A' <= x <= 'Z', "'A' <= x <= 'Z'")])),
    Scope(And([
        MatchObject(lambda x: '0' <= x <= '9', "'0' <= x <= '9'")]))])
rules['Parser.space'] = Or([
    Scope(And([
        Star(Or([
            Scope(And([
                And([
                    MatchObject(lambda x: x == ' ', "x == ' '")])])),
            Scope(And([
                And([
                    MatchObject(lambda x: x == '\n', "x == '\\n'")])]))]))]))])
rules['CodeGenerator.Namespace'] = Or([
    Scope(And([
        Bind('x', MatchObject(lambda x: True, 'True')),
        Bind('ys', Star(MatchRule('CodeGenerator.ast'))),
        Action(lambda self: self.bind('namespace', self.lookup('x'), lambda: join([
            self.lookup('ys')])))]))])
rules['CodeGenerator.Rule'] = Or([
    Scope(And([
        Bind('x', MatchObject(lambda x: True, 'True')),
        Bind('y', MatchRule('CodeGenerator.ast')),
        Action(lambda self: join([
            "rules['",
            self.lookup('namespace'),
            '.',
            self.lookup('x'),
            "'] = ",
            self.lookup('y'),
            '\n']))]))])
rules['CodeGenerator.Or'] = Or([
    Scope(And([
        Bind('x', MatchRule('CodeGenerator.astList')),
        Action(lambda self: join([
            'Or([',
            self.lookup('x'),
            '])']))]))])
rules['CodeGenerator.Scope'] = Or([
    Scope(And([
        Bind('x', MatchRule('CodeGenerator.ast')),
        Action(lambda self: join([
            'Scope(',
            self.lookup('x'),
            ')']))]))])
rules['CodeGenerator.And'] = Or([
    Scope(And([
        Bind('x', MatchRule('CodeGenerator.astList')),
        Action(lambda self: join([
            'And([',
            self.lookup('x'),
            '])']))]))])
rules['CodeGenerator.Bind'] = Or([
    Scope(And([
        Bind('x', MatchObject(lambda x: True, 'True')),
        Bind('y', MatchRule('CodeGenerator.ast')),
        Action(lambda self: join([
            'Bind(',
            self.lookup('repr')(
                self.lookup('x')),
            ', ',
            self.lookup('y'),
            ')']))]))])
rules['CodeGenerator.Star'] = Or([
    Scope(And([
        Bind('x', MatchRule('CodeGenerator.ast')),
        Action(lambda self: join([
            'Star(',
            self.lookup('x'),
            ')']))]))])
rules['CodeGenerator.Not'] = Or([
    Scope(And([
        Bind('x', MatchRule('CodeGenerator.ast')),
        Action(lambda self: join([
            'Not(',
            self.lookup('x'),
            ')']))]))])
rules['CodeGenerator.MatchCallRule'] = Or([
    Scope(And([
        Action(lambda self: join([
            "MatchCallRule('",
            self.lookup('namespace'),
            "')"]))]))])
rules['CodeGenerator.MatchRule'] = Or([
    Scope(And([
        Bind('x', MatchObject(lambda x: True, 'True')),
        Action(lambda self: join([
            "MatchRule('",
            self.lookup('namespace'),
            '.',
            self.lookup('x'),
            "')"]))]))])
rules['CodeGenerator.MatchObject'] = Or([
    Scope(And([
        Bind('x', MatchRule('CodeGenerator.ast')),
        Action(lambda self: join([
            'MatchObject(lambda x: ',
            self.lookup('x'),
            ', ',
            self.lookup('repr')(
                self.lookup('x')),
            ')']))]))])
rules['CodeGenerator.MatchList'] = Or([
    Scope(And([
        Bind('x', MatchRule('CodeGenerator.ast')),
        Action(lambda self: join([
            'MatchList(',
            self.lookup('x'),
            ')']))]))])
rules['CodeGenerator.Any'] = Or([
    Scope(And([
        Action(lambda self: join([
            'True']))]))])
rules['CodeGenerator.Eq'] = Or([
    Scope(And([
        Bind('x', MatchObject(lambda x: True, 'True')),
        Action(lambda self: join([
            'x == ',
            self.lookup('repr')(
                self.lookup('x'))]))]))])
rules['CodeGenerator.Range'] = Or([
    Scope(And([
        Bind('x', MatchObject(lambda x: True, 'True')),
        Bind('y', MatchObject(lambda x: True, 'True')),
        Action(lambda self: join([
            self.lookup('repr')(
                self.lookup('x')),
            ' <= x <= ',
            self.lookup('repr')(
                self.lookup('y'))]))]))])
rules['CodeGenerator.Action'] = Or([
    Scope(And([
        Bind('x', MatchRule('CodeGenerator.ast')),
        Action(lambda self: join([
            'Action(lambda self: ',
            self.lookup('x'),
            ')']))]))])
rules['CodeGenerator.Set'] = Or([
    Scope(And([
        Bind('x', MatchObject(lambda x: True, 'True')),
        Bind('y', MatchRule('CodeGenerator.ast')),
        Bind('z', MatchRule('CodeGenerator.ast')),
        Action(lambda self: join([
            'self.bind(',
            self.lookup('repr')(
                self.lookup('x')),
            ', ',
            self.lookup('y'),
            ', lambda: ',
            self.lookup('z'),
            ')']))]))])
rules['CodeGenerator.String'] = Or([
    Scope(And([
        Bind('x', MatchObject(lambda x: True, 'True')),
        Action(lambda self: self.lookup('repr')(
            self.lookup('x')))]))])
rules['CodeGenerator.List'] = Or([
    Scope(And([
        Bind('x', MatchRule('CodeGenerator.astList')),
        Action(lambda self: join([
            'concat([',
            self.lookup('x'),
            '])']))]))])
rules['CodeGenerator.ListItem'] = Or([
    Scope(And([
        Bind('x', MatchObject(lambda x: True, 'True')),
        Bind('y', MatchRule('CodeGenerator.ast')),
        Action(lambda self: join([
            'splice(',
            self.lookup('repr')(
                self.lookup('x')),
            ', ',
            self.lookup('y'),
            ')']))]))])
rules['CodeGenerator.Format'] = Or([
    Scope(And([
        Bind('x', MatchRule('CodeGenerator.astList')),
        Action(lambda self: join([
            'join([',
            self.lookup('x'),
            '])']))]))])
rules['CodeGenerator.Indent'] = Or([
    Scope(And([
        Bind('x', MatchRule('CodeGenerator.ast')),
        Action(lambda self: join([
            'indent(',
            self.lookup('x'),
            ', ',
            "self.lookup('indentprefix'))"]))]))])
rules['CodeGenerator.Call'] = Or([
    Scope(And([
        Bind('x', MatchRule('CodeGenerator.ast')),
        Bind('y', MatchRule('CodeGenerator.astList')),
        Action(lambda self: join([
            self.lookup('x'),
            '(',
            self.lookup('y'),
            ')']))]))])
rules['CodeGenerator.Lookup'] = Or([
    Scope(And([
        Bind('x', MatchObject(lambda x: True, 'True')),
        Action(lambda self: join([
            'self.lookup(',
            self.lookup('repr')(
                self.lookup('x')),
            ')']))]))])
rules['CodeGenerator.astList'] = Or([
    Scope(And([
        Bind('xs', Star(MatchRule('CodeGenerator.ast'))),
        Action(lambda self: join([
            '\n',
            indent(join([
                self.lookup('join')(
                    self.lookup('xs'),
                    ',\n')]), self.lookup('indentprefix'))]))]))])
rules['CodeGenerator.asts'] = Or([
    Scope(And([
        Bind('xs', Star(MatchRule('CodeGenerator.ast'))),
        Not(MatchObject(lambda x: True, 'True')),
        Action(lambda self: join([
            self.lookup('xs')]))]))])
rules['CodeGenerator.ast'] = Or([
    Scope(And([
        MatchList(And([
            Bind('x', MatchCallRule('CodeGenerator'))]))]))])
if __name__ == "__main__":
    import sys
    def read(path):
        if path == "-":
            return sys.stdin.read()
        with open(path) as f:
            return f.read()
    args = sys.argv[1:] or ["--compile", "-"]
    while args:
        command = args.pop(0)
        if command == "--support":
            sys.stdout.write(SUPPORT)
        elif command == "--copy":
            sys.stdout.write(read(args.pop(0)))
        elif command == "--embed":
            sys.stdout.write("{} = {}\n".format(
                args.pop(0),
                repr(read(args.pop(0)))
            ))
        elif command == "--compile":
            sys.stdout.write(compile_chain(
                ["Parser.file", "CodeGenerator.asts"],
                read(args.pop(0))
            ))
        else:
            sys.exit("ERROR: Unknown command '{}'".format(command))
