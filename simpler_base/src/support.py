rules = {}

class Stream:

    def __init__(self, items):
        self.items = items
        self.scopes = []
        self.index = 0
        self.latest_error = None

    def operator_or(self, matchers):
        for matcher in matchers:
            state = self.save()
            try:
                return matcher.run(self)
            except MatchError:
                self.restore(state)
        self.error("no or match")

    def operator_and(self, matchers):
        result = self.action(lambda self: None)
        for matcher in matchers:
            result = matcher.run(self)
        return result

    def operator_star(self, matcher):
        results = []
        while True:
            state = self.save()
            try:
                results.append(matcher.run(self))
            except MatchError:
                self.restore(state)
                break
        return self.action(lambda self: [x.eval(self.runtime) for x in results])

    def operator_not(self, matcher):
        state = self.save()
        try:
            matcher.run(self)
        except MatchError:
            return self.action(lambda self: None)
        finally:
            self.restore(state)
        self.error("not matched")

    def action(self, fn):
        return SemanticAction(self.scopes[-1], fn)

    def save(self):
        return (self.items, [dict(x) for x in self.scopes], self.index)

    def restore(self, values):
        (self.items, self.scopes, self.index) = values

    def with_scope(self, matcher):
        self.scopes.append({})
        result = matcher.run(self)
        self.scopes.pop(-1)
        return result

    def bind(self, name, semantic_action):
        self.scopes[-1][name] = semantic_action
        return semantic_action

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

class SemanticAction:

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

class Runtime:

    def __init__(self, extra={"len": len, "repr": repr}):
        self.vars = extra

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
