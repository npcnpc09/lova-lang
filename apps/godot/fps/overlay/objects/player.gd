extends CharacterBody3D

# The kit's player.gd with its rules taken out.  What was
# handle_controls, handle_gravity, move_and_slide, action_shoot,
# action_jump, the enemies' timers and rays -- all of it -- runs in
# lib/fps.lova, in the LOVA runtime this node holds (native/lova-godot,
# the native runtime as a GDExtension class).  This script reads the
# keys and the mouse, hands them to the rules once a physics tick, and
# puts what the rules answer into the kit's own nodes: the player's
# transform, the camera's pitch and dip, the weapon in the hand, the
# enemies' places, the marks a shot leaves.  Sounds, muzzle flashes and
# the weapon-change tween are the kit's, played on the ticks the rules
# say they happen.
#
# The rules count in integers: a metre is F, a turn is A.  Nothing
# fractional crosses into the runtime; it refuses a float by name.

@export_subgroup("Weapons")
@export var weapons: Array[Weapon] = []
@export var crosshair: TextureRect

const F := 65536.0            # a metre, in the rules
const A := 16384.0            # a turn
const MOUSE_SENSITIVITY := 700.0
const BUDGET := 50_000_000    # steps a call may take
const PROGRAM := "res://lova/fps_godot.hex"

var weapon: Weapon
var weapon_index := 0
var mouse_captured := true
var mouse_delta := Vector2.ZERO
var container_offset = Vector3(1.2, -1.1, -2.75)
var tween: Tween

signal health_updated

@onready var camera = $Head/Camera
@onready var muzzle = $Head/Camera/SubViewportContainer/SubViewport/CameraItem/Muzzle
@onready var container = $Head/Camera/SubViewportContainer/SubViewport/CameraItem/Container
@onready var sound_footsteps = $SoundFootsteps

var rt: LovaRuntime
var fn := {}                  # the program's functions, by name
var world                     # the world, a handle the runtime holds
var enemies: Array = []       # the enemy nodes, in the rules' order
var bound := false
var health := 100
var restarts := 0
var last_position := Vector3.ZERO
var tick_steps := 0
var tick_usec := 0
var readout: Label
var shot_path := ""           # --shot=<png>: a scripted run, a picture, quit
var movie_ticks := 0          # --movie=<ticks>: a longer scripted run, then quit
var ticks := 0
var last_scene: Array = []
var caption: Label
var done_at := 0              # the tick the demo ran out of reachable enemies


func _ready():
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	rt = LovaRuntime.new()
	var hex := FileAccess.get_file_as_string(PROGRAM).strip_edges()
	if not rt.open(hex, BUDGET, 10000):
		push_error("LOVA: the program did not open: " + rt.error())
		return
	for name in ["new", "tick", "input", "scene"]:
		fn[name] = rt.get(name)
	world = fn["new"]
	weapon = weapons[weapon_index]
	initiate_change_weapon(weapon_index)
	_add_readout()
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot="):
			shot_path = a.substr(7)
		if a.begins_with("--movie="):
			movie_ticks = int(a.substr(8))
			_add_caption()


# The enemy nodes are ready after this one, so they are matched to the
# rules' enemies on the first tick: each node to the rules' enemy that
# stands where it does.
func _bind_enemies(scene: Array):
	var nodes := get_tree().get_nodes_in_group("lova_enemies")
	enemies.clear()
	for e in scene[1]:
		var at := Vector3(e[0] / F, e[1] / F, e[2] / F)
		var best = null
		var best_d := INF
		for n in nodes:
			var d = n.position.distance_to(at)
			if d < best_d:
				best_d = d
				best = n
		enemies.append(best)
	bound = true


func _input(event):
	if event is InputEventMouseMotion and mouse_captured:
		mouse_delta += event.relative


func _physics_process(delta):
	if rt == null or not rt.is_open():
		return
	if Input.is_action_just_pressed("mouse_capture"):
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
		mouse_captured = true
	if Input.is_action_just_pressed("mouse_capture_exit"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
		mouse_captured = false
		mouse_delta = Vector2.ZERO

	# What is held this tick, in the rules' units.  The kit turns by
	# `-relative / mouse_sensitivity` radians; A / (2 pi) of a turn is
	# a radian.
	var mx := int(Input.is_action_pressed("move_right")) - int(Input.is_action_pressed("move_left"))
	var mz := int(Input.is_action_pressed("move_back")) - int(Input.is_action_pressed("move_forward"))
	var jump := 1 if Input.is_action_just_pressed("jump") else 0
	var shoot := 1 if Input.is_action_pressed("shoot") else 0
	var toggle := 1 if Input.is_action_just_pressed("weapon_toggle") else 0
	var sens := A / (MOUSE_SENSITIVITY * TAU)
	var dyaw := -mouse_delta.x * sens
	var dpitch := -mouse_delta.y * sens
	mouse_delta = Vector2.ZERO
	var turn := 120.0 * A / 360.0 / 60.0    # the kit's gamepad turn, a tick
	dyaw += turn * (int(Input.is_action_pressed("camera_left")) - int(Input.is_action_pressed("camera_right")))
	dpitch += turn * (int(Input.is_action_pressed("camera_up")) - int(Input.is_action_pressed("camera_down")))
	if shot_path != "":
		# Nobody at the keys: walk, turn toward the enemies, shoot.
		mx = 0
		mz = -1 if ticks < 45 else 0
		dyaw = turn if 45 <= ticks and ticks < 75 else 0.0
		dpitch = 0.0
		shoot = 1 if ticks >= 60 else 0
		jump = 1 if ticks == 20 else 0
		toggle = 0
	elif movie_ticks > 0:
		var plan := _movie_input()
		mx = plan[0]
		mz = plan[1]
		jump = plan[2]
		shoot = plan[3]
		toggle = plan[4]
		dyaw = plan[5]
		dpitch = plan[6]
	ticks += 1

	var held = rt.call(fn["input"], [mx, mz, jump, shoot, toggle, int(round(dyaw)), int(round(dpitch))])
	var t0 := Time.get_ticks_usec()
	var next = rt.call(fn["tick"], [world, held])
	if next == null:
		push_error("LOVA: the tick trapped: " + rt.error())
		rt.release([held])
		return
	tick_usec = Time.get_ticks_usec() - t0
	tick_steps = rt.steps()
	rt.release([world, held])
	world = next

	var scene = rt.call(fn["scene"], [world])
	if scene == null:
		push_error("LOVA: scene trapped: " + rt.error())
		return
	if not bound:
		_bind_enemies(scene)
	last_scene = scene
	_apply(scene, delta)
	if movie_ticks > 0 and (ticks >= movie_ticks or (done_at > 0 and ticks >= done_at + 150)):
		print("movie: ", ticks, " ticks")
		get_tree().quit()


# The demo's choreography, a tick at a time: walk in, jump, look round,
# then turn to the nearest standing enemy and shoot until none stands,
# changing weapon on the way.  The aim is computed from what the rules
# reported last tick -- the enemies' places in F -- so the demo's hand
# on the mouse is steadier than a person's, and everything it hits is
# hit by the rules' own ray.
func _movie_input() -> Array:
	var turn := 120.0 * A / 360.0 / 60.0
	var max_turn := 4.0 * A / 360.0          # degrees a tick the aim may move
	var mx := 0
	var mz := 0
	var jump := 0
	var shoot := 0
	var toggle := 0
	var dyaw := 0.0
	var dpitch := 0.0
	if last_scene.size() != 3:
		return [0, 0, 0, 0, 0, 0.0, 0.0]
	var p: Array = last_scene[0]
	var px: float = p[0] / F
	var pz: float = p[2] / F
	# The home platform is five metres across at the origin; the demo
	# never leaves it, because the rules' shots reach ten metres and
	# the blaster's knockback of forty would throw it off the edge.
	var at_home := absf(px) < 2.0 and absf(pz) < 2.0
	if ticks < 30:
		mz = -1 if pz > -1.2 else 0                # a few steps in
		jump = 1 if ticks == 12 else 0
	elif ticks < 150:
		dyaw = turn * 0.5                          # a look round
	else:
		var eye := Vector3(px, p[1] / F + 1.0 + p[5] / F, pz)
		var target = null
		var best := INF
		var standing := 0
		for e in last_scene[1]:
			if e[4] != 1:
				continue
			standing += 1
			var at := Vector3(e[0] / F, e[1] / F + 0.25, e[2] / F)
			var d := eye.distance_to(at)
			if d < best:
				best = d
				target = at
		if target != null:
			var d: Vector3 = target - eye
			var want_yaw := atan2(-d.x, -d.z)
			var have_yaw: float = p[3] * TAU / A
			var err_yaw := wrapf(want_yaw - have_yaw, -PI, PI)
			var want_pitch := atan2(d.y, Vector2(d.x, d.z).length())
			var have_pitch: float = p[4] * TAU / A
			var err_pitch: float = want_pitch - have_pitch
			dyaw = clampf(err_yaw * A / TAU, -max_turn, max_turn)
			dpitch = clampf(err_pitch * A / TAU, -max_turn, max_turn)
			var aligned := absf(err_yaw) < deg_to_rad(2.5) and absf(err_pitch) < deg_to_rad(2.5)
			var reachable := best < 10.5           # the rules' shot is ten metres
			shoot = 1 if aligned and reachable and ticks > 170 else 0
			if aligned and best > 6.5 and at_home:
				mz = -1                            # closer, while the platform lasts
			if not reachable and not at_home and done_at == 0:
				done_at = ticks                    # the rest are out of range: the end
		elif done_at == 0:
			done_at = ticks
		# the repeater for the first two (knockback ten), the blaster --
		# three shots a trigger and a kick of forty -- for the third
		toggle = 1 if ticks == 155 or (standing == 2 and p[7] == 1) else 0
	return [mx, mz, jump, shoot, toggle, dyaw, dpitch]


func _add_caption():
	var hud = get_parent().get_node_or_null("HUD")
	if hud == null:
		return
	caption = Label.new()
	caption.text = "rules: lib/fps.lova, 704 lines of LOVA, in the LOVA VM inside Godot   |   picture: Kenney's FPS kit, drawn by Godot"
	caption.add_theme_font_size_override("font_size", 18)
	caption.add_theme_color_override("font_color", Color(1, 1, 1, 0.9))
	caption.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.6))
	caption.add_theme_constant_override("shadow_offset_x", 1)
	caption.add_theme_constant_override("shadow_offset_y", 1)
	caption.anchor_top = 1.0
	caption.anchor_bottom = 1.0
	caption.anchor_left = 0.0
	caption.anchor_right = 1.0
	caption.offset_top = -40
	caption.offset_bottom = -12
	caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hud.add_child(caption)


# The rules' answer, into the kit's nodes.
func _apply(scene: Array, delta: float):
	var p: Array = scene[0]
	var at := Vector3(p[0] / F, p[1] / F, p[2] / F)
	if ticks == 1:
		last_position = at
	var moved := (at - last_position) / delta
	last_position = at
	position = at
	rotation.y = p[3] * TAU / A
	camera.rotation.x = p[4] * TAU / A
	camera.position.y = p[5] / F

	# The weapon sways against the velocity, as the kit's does.
	container.position = lerp(container.position, container_offset - (basis.inverse() * moved / 30), delta * 10)

	# Footsteps while walking on something.
	sound_footsteps.stream_paused = not (absf(moved.x) > 1 or absf(moved.z) > 1) or absf(moved.y) > 0.5

	var new_health: int = p[6]
	var hurt := new_health < health
	if new_health != health:
		health = new_health
		health_updated.emit(health)

	if p[7] != weapon_index:
		initiate_change_weapon(p[7])
		Audio.play("sounds/weapon_change.ogg")

	if p[8]:
		_shot()

	if p[10] != restarts:
		restarts = p[10]
		_restarted()

	# The enemies.
	var es: Array = scene[1]
	for i in range(min(es.size(), enemies.size())):
		var e: Array = es[i]
		var node = enemies[i]
		if node == null:
			continue
		node.apply(Vector3(e[0] / F, e[1] / F, e[2] / F), e[4] == 1, e[5], e[6] == 1 and hurt)

	# The marks shots leave: the kit's impact sprite, where the rules
	# put it, on the tick they made it.
	if scene[2] != null:
		for m in scene[2]:
			if m[3] == 1:
				_impact(Vector3(m[0] / F, m[1] / F, m[2] / F))

	if readout:
		var standing := 0
		for e in es:
			if e[4] == 1:
				standing += 1
		readout.text = "LOVA tick %s steps / %.2f ms     enemies standing %d" % [_group(tick_steps), tick_usec / 1000.0, standing]
	if shot_path != "" and ticks == 120:
		_take_shot()


func _take_shot():
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	image.save_png(shot_path)
	print("shot: ", shot_path, " after ", ticks, " ticks; last tick ", tick_steps, " steps, ", tick_usec, " us")
	get_tree().quit()


func _shot():
	Audio.play(weapon.sound_shoot)
	muzzle.play("default")
	muzzle.rotation_degrees.z = randf_range(-45, 45)
	muzzle.scale = Vector3.ONE * randf_range(0.40, 0.75)
	muzzle.position = container.position - weapon.muzzle_position
	container.position.z += 0.25


func _impact(at: Vector3):
	var impact = preload("res://objects/impact.tscn")
	var impact_instance = impact.instantiate()
	impact_instance.play("shot")
	get_tree().root.add_child(impact_instance)
	impact_instance.position = at
	impact_instance.look_at(camera.global_transform.origin, Vector3.UP, true)


# The kit reloads the scene when the player falls or runs out of
# health; the rules start a new game in the same world instead, so the
# nodes are put back rather than rebuilt.
func _restarted():
	for node in enemies:
		if node:
			node.reset()
	health = 100
	health_updated.emit(health)


func _add_readout():
	var hud = get_parent().get_node_or_null("HUD")
	if hud == null:
		return
	readout = Label.new()
	readout.position = Vector2(16, 16)
	readout.add_theme_font_size_override("font_size", 18)
	readout.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.6))
	readout.add_theme_constant_override("shadow_offset_x", 1)
	readout.add_theme_constant_override("shadow_offset_y", 1)
	readout.add_theme_color_override("font_color", Color(1, 1, 1, 0.8))
	hud.add_child(readout)


static func _group(n: int) -> String:
	var s := str(n)
	var out := ""
	var count := 0
	for i in range(s.length() - 1, -1, -1):
		out = s[i] + out
		count += 1
		if count % 3 == 0 and i > 0:
			out = " " + out
	return out


# --- the weapon in the hand: the kit's own code ------------------------

func initiate_change_weapon(index):
	weapon_index = index
	tween = get_tree().create_tween()
	tween.set_ease(Tween.EASE_OUT_IN)
	tween.tween_property(container, "position", container_offset - Vector3(0, 1, 0), 0.1)
	tween.tween_callback(change_weapon)


func change_weapon():
	weapon = weapons[weapon_index]
	for n in container.get_children():
		container.remove_child(n)
	var weapon_model = weapon.model.instantiate()
	container.add_child(weapon_model)
	weapon_model.position = weapon.position
	weapon_model.rotation_degrees = weapon.rotation
	for child in weapon_model.find_children("*", "MeshInstance3D"):
		child.layers = 2
	crosshair.texture = weapon.crosshair
