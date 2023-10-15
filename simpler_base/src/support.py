def operator_or(stream, matchers):
    for matcher in matchers:
        state = stream.save()
        try:
            return matcher.run(stream)
        except MatchError:
            stream.restore(state)
    stream.error("no or match")

def operator_and(stream, matchers):
    result = stream.action(lambda self: None)
    for matcher in matchers:
        result = matcher.run(stream)
    return result

def operator_star(stream, matcher):
    results = []
    while True:
        state = stream.save()
        try:
            results.append(matcher.run(stream))
        except MatchError:
            stream.restore(state)
            break
    return stream.action(lambda self: [x.eval(self.runtime) for x in results])

def operator_not(stream, matcher):
    state = stream.save()
    try:
        matcher.run(stream)
    except MatchError:
        return stream.action(lambda self: None)
    finally:
        stream.restore(state)
    stream.error("not matched")

class RuntimeAction:

    def __init__(self, scope, fn):
        self.scope = scope
        self.fn = fn

    def eval(self, runtime):
        self.runtime = runtime
        return self.fn(self)

    def bind(self, name, value, continuation):
        self.runtime = self.runtime.bind(name, value)
        return continuation()

    def lookup(self, name):
        if name in self.scope:
            return self.scope[name].eval(self.runtime)
        else:
            return self.runtime.lookup(name)

class Stream:

    def __init__(self, items):
        self.items = items
        self.scopes = []
        self.index = 0
        self.latest_error = None

    def action(self, fn):
        return RuntimeAction(self.scopes[-1], fn)

    def save(self):
        return (self.items, [dict(x) for x in self.scopes], self.index)

    def restore(self, values):
        (self.items, self.scopes, self.index) = values

    def with_scope(self, matcher):
        self.scopes.append({})
        result = matcher.run(self)
        self.scopes.pop(-1)
        return result

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
        if not self.latest_error or self.index > self.latest_error[2]:
            self.latest_error = (name, self.items, self.index)
        raise MatchError(*self.latest_error)

class MatchError(Exception):

    def __init__(self, name, items, index):
        Exception.__init__(self, name)
        self.items = items
        self.index = index

class Runtime:

    def __init__(self, extra={}):
        self.vars = dict({"len": len, "repr": repr}, **extra)

    def bind(self, name, value):
        return Runtime(dict(self.vars, **{name: value}))

    def lookup(self, name):
        if name in self.vars:
            return self.vars[name]
        else:
            return getattr(self, name)

    def append(self, list, thing):
        list.append(thing)

    def join(self, items, delimiter=""):
        return delimiter.join(
            self.join(item, delimiter) if isinstance(item, list) else str(item)
            for item in items
        )

    def indent(self, text, prefix="    "):
        return "".join(prefix+line for line in text.splitlines(True))

    def splice(self, depth, item):
        if depth == 0:
            return [item]
        else:
            return self.concat([self.splice(depth-1, subitem) for subitem in item])

    def concat(self, lists):
        return [x for xs in lists for x in xs]

def compile_chain(grammars, source):
    import os
    import sys
    import pprint
    runtime = Runtime()
    for rule in grammars:
        try:
            source = rules[rule].run(Stream(source)).eval(runtime)
        except MatchError as e:
            marker = "<ERROR POSITION>"
            if os.isatty(sys.stderr.fileno()):
                marker = f"\033[0;31m{marker}\033[0m"
            if isinstance(e.items, str):
                stream_string = e.items[:e.index] + marker + e.items[e.index:]
            else:
                stream_string = pprint.pformat(e.items)
            sys.exit("ERROR: {}\nPOSITION: {}\nSTREAM:\n{}".format(
                str(e),
                e.index,
                runtime.indent(stream_string)
            ))
    return source

rules = {}
