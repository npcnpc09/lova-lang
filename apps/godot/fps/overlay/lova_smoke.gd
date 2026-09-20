extends SceneTree

# A run with no window: `godot --headless --path project --script
# res://lova_smoke.gd`.  Opens the program, runs three hundred ticks
# of walking, jumping and shooting, prints the scene and the cost, and
# shows the runtime refusing a float.  `build.py --smoke` runs it.


func _init():
	var rt = LovaRuntime.new()
	print("ping: ", rt.ping())
	var hex = FileAccess.get_file_as_string("res://lova/fps_godot.hex").strip_edges()
	if not rt.open(hex, 50_000_000, 10000):
		push_error("open failed: " + rt.error())
		quit(1)
		return
	var new_game = rt.get("new")
	var tick = rt.get("tick")
	var input = rt.get("input")
	var scene = rt.get("scene")
	var w = new_game
	var held = rt.call(input, [0, -1, 1, 1, 0, 0, 0])
	var t0 = Time.get_ticks_usec()
	var steps := 0
	for i in 300:
		var n = rt.call(tick, [w, held])
		if n == null:
			push_error("tick trapped: " + rt.error())
			quit(1)
			return
		steps += rt.steps()
		rt.release([w])
		w = n
	var us = Time.get_ticks_usec() - t0
	print("300 ticks: %d steps, %.1f ms, %.3f ms a tick" % [steps, us / 1000.0, us / 300000.0])
	print("scene: ", rt.call(scene, [w]))
	var bad = rt.call(tick, [w, 1.5])
	print("a float in: ", bad, " -- ", rt.error())
	var trap = rt.call(tick, [w, w])
	print("a world for an input: ", trap, " -- ", rt.error())
	quit(0)
