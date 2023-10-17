This repository will host the base implementation of RLMeta as well as
modifications to it.

## Ideals

* How small, understandable can we make the core?

* Clarity: How does it affect understandability/learnability/readability?
* Size: Lines of code.
* Flexibility: How easy is it to modify RLMeta to be what you need?
* Performance: How fast does it compile?

## Ideas

* LISP style semantic actions
* Compile semantic actions to more efficient code
    * Should not "Lookup" match variables more than once
* Memoization as add-on
* Left associate operators as add-on
* Smaller diff in modification -> large flexibility
* Remove indent/format syntax from RLMeta?
* Call ast something else in assembler? Tree? Code?
* Use LISP style function calls and support operators and function names (would
  make QOI more readable)
* Let LISP syntax instead of multiple `->` in semantic actions?

## TODO

[ ] params compile_chain

[ ] Can fail_pos be handled better?

    [ ] MatchError probably has wrong stream if error occurs deep down

[ ] Can support library (and new Runtime) become smaller?

[ ] Substream matching should return substream as action

[ ] What should an empty ["And"] return? Undefined or default None?

[ ] `?` operator should return empty list (in case of no match) or list with
    one item (in case of match).

[ ] Why not better error message when action wrong? Why index wrong?

      Action        = .:xs
      Action        = .*:xs

    [ ] Wrong pos is reported for "Not" instruction.

    -   "Not" messes up latest_fail_pos in general. It should perhaps be
        disabled during a "Not"?

[ ] Poster with intermediate versions (output from parser, etc.) shown.

    [ ] Interactive on the web. (Requires JS version.)

    [ ] Add DEBUG flag that outputs source between passes.

[ ] Try to port to JS to see how flexible it is?

[ ] Rename ast to tree?

[ ] Lookup concat/splice/join/indent?
