# lova-godot -- the native runtime as a Godot class

A GDExtension that links `lova-rt` and exposes one class, `LovaRuntime`,
to GDScript.  Nothing crosses a process boundary: the runtime is in
Godot's process, and a call is a function call.  The contract is the
same as the stdio binary's, `spec/native-runtime-protocol.md`; this
crate carries it as Godot values.

```bash
cd native/lova-godot
cargo build --release          # target/release/lova_godot.dll (.so, .dylib)
```

Rust 1.94 or later (godot-rust 0.5.5); built against Godot's 4.6 API,
so Godot 4.6 or later loads it.  A project needs a `.gdextension`
manifest pointing at the library -- `apps/godot/fps/overlay/lova.gdextension`
is one -- and, when run without the editor having imported the
project, `.godot/extension_list.cfg` naming the manifest.

## The class

```gdscript
var rt := LovaRuntime.new()
var hex := FileAccess.get_file_as_string("res://lova/program.hex").strip_edges()
if not rt.open(hex, 50_000_000, 10_000):
    push_error(rt.error())
var tick := rt.get("tick")                   # a handle on a closure
var world := rt.get("new")                   # a handle on a record
world = rt.call(tick, [world, held])         # null on a trap; rt.error(), rt.anomaly()
print(rt.steps())                            # this call's steps
rt.release([old_world])
```

| Method | Protocol op | What |
|---|---|---|
| `open(hex, max_steps, max_depth) -> bool` | `session` | evaluate the program, keep it |
| `get(name) -> Variant` | `get` on the program's value | a field by name |
| `get_in(map, key) -> Variant` | `get` | a field of any held map |
| `call(fn, args: Array) -> Variant` | `call` | apply, one argument at a time |
| `release(handles: Array)` | `release` | drop handles |
| `close()` | `close` | end the session |
| `request(json: String) -> String` | any | the protocol raw |
| `ping() -> Dictionary` | `ping` | version, evaluator, unsupported ops |
| `steps()`, `error()`, `anomaly()`, `is_open()`, `api_handle()`, `set_max_steps(n)` | | |

Values cross as the protocol encodes them: an integer is an `int`
(beyond 2^53, `{"int": "digits"}`), a text a `String`, a list an
`Array`, `nil` null, and a map, closure, program or population a
`Dictionary {"ref": id}` naming a value the session holds.  A `bool`
enters as 0 or 1.  A float is refused with a message naming it: LOVA
has no floats, and a Vector3 that leaks in unconverted is the mistake
a game host makes.

## Inside

The evaluator runs on its own thread with a gigabyte of stack, as the
stdio binary does (`main.rs`): a LOVA call is several Rust frames and
the depth ceiling is ten thousand, which Godot's main thread cannot
hold.  A request is sent over a channel and its reply waited for, so a
call is synchronous to the script.  The thread owns the sessions and
ends when the `LovaRuntime` is freed.  Small allocations go through
`lova_rt::alloc::Pooled`, as in the binary.
