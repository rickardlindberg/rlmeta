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
            except MatchError:
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
            except MatchError:
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
            except MatchError:
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
        raise MatchError(*self.latest_error)

class MatchError(Exception):
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
            "indent": indent,
            "join": join,
            "repr": repr,
        }

    def bind(self, name, value):
        self.vars[name] = value

    def lookup(self, name):
        return self.vars[name]

def indent(text, prefix="    "):
    return "".join(prefix+line for line in text.splitlines(True))

def compile_chain(grammars, source):
    import os
    import sys
    import pprint
    for rule in grammars:
        try:
            source = rules[rule].run(Stream(source)).eval(Runtime())
        except MatchError as e:
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
