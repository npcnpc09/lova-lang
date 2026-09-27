extends Node3D

# 東方天球譚 -- a three-dimensional danmaku duel, a Touhou Project fan game.
#
# Everything that decides is lib/danmaku.lova, run by the LovaRuntime
# extension (native/lova-godot).  This script reads the keys, hands them
# to the rules once a physics tick, and draws what the rules answer:
# the maiden, the witch, every bullet and amulet, the HUD.  It builds
# the whole scene in code -- sky, arena, trees, the two figures from
# primitives, the bullets as MultiMeshes -- and synthesises its sounds
# and its music, so the project has no asset of anyone else's in it.
#
# The rules count in integers: a metre is F.  Nothing fractional
# crosses into the runtime; it refuses a float by name.

const F := 65536.0
const BUDGET := 50_000_000
const PROGRAM := "res://lova/danmaku_godot.hex"
const CAP := 4000                       # bullets a MultiMesh can hold
const SHOT_CAP := 256

const CARDS := [
	["通常攻撃", "Non-Spell"],
	["星符「ギャラクシースパイラル」", "Star Sign \"Galaxy Spiral\""],
	["恋符「スターダストレイン」", "Love Sign \"Stardust Rain\""],
]
const BOSS_NAME := "霧雨 魔理沙"
const BOSS_NAME_EN := "Marisa Kirisame"

# Drawn radius of each bullet kind (the rules' hit radius is smaller:
# 0.1, 0.2, 0.4) and its colour.
const DRAW_R := [0.17, 0.34, 0.6]
const KIND_COLOR := [Color(1.0, 0.25, 0.45), Color(1.0, 0.85, 0.2), Color(0.35, 0.55, 1.0)]

var rt: LovaRuntime
var fn := {}
var world
var hud_data: Array = []
var bullets: Array = []
var shots: Array = []
var ticks := 0
var tick_steps := 0
var tick_usec := 0
var scene_usec := 0

# scripted runs
var shot_path := ""
var shot_at := 600
var movie_ticks := 0
var demo := false
var start_phase := -1
var smoke := false

# nodes
var cam: Camera3D
var maiden: Node3D
var witch: Node3D
var circle: MeshInstance3D
var hitbox: MeshInstance3D
var graze_ring: MeshInstance3D
var maiden_shadow: MeshInstance3D
var witch_shadow: MeshInstance3D
var mm := []                            # a MultiMesh per bullet kind
var mm_shadow: MultiMesh
var mm_shots: MultiMesh
var bufs := []
var shadow_buf := PackedFloat32Array()
var shot_buf := PackedFloat32Array()
var bomb_orbs: Array = []
var bomb_t := -1
var shake := 0.0
var cam_pos := Vector3.ZERO
var cam_look := Vector3.ZERO
var witch_mat: StandardMaterial3D

# HUD
var font: SystemFont
var card_label: Label
var card_en: Label
var timer_label: Label
var hp_bar: ColorRect
var hp_back: ColorRect
var boss_label: Label
var side_label: Label
var readout: Label
var banner: Label
var banner_sub: Label
var banner_t := 0
var center_msg: Label
var help_label: Label

# sound
var sfx := {}
var players: Array = []
var music: AudioStreamPlayer
var last_graze_sfx := 0
var last_hit_sfx := 0
var last_k := 1


func _ready():
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--shot="):
			shot_path = a.substr(7)
		elif a.begins_with("--at="):
			shot_at = int(a.substr(5))
		elif a.begins_with("--movie="):
			movie_ticks = int(a.substr(8))
		elif a.begins_with("--phase="):
			start_phase = int(a.substr(8))
		elif a == "--demo":
			demo = true
		elif a == "--smoke":
			smoke = true
	if shot_path != "" or movie_ticks > 0:
		demo = true

	rt = LovaRuntime.new()
	var hex := FileAccess.get_file_as_string(PROGRAM).strip_edges()
	if not rt.open(hex, BUDGET, 10000):
		push_error("LOVA: the program did not open: " + rt.error())
		get_tree().quit(1)
		return
	for name in ["new", "tick", "input", "scene", "at"]:
		fn[name] = rt.get(name)
	if start_phase >= 0:
		world = rt.call(fn["at"], [start_phase])
	else:
		world = fn["new"]

	font = SystemFont.new()
	font.font_names = PackedStringArray(["Yu Mincho", "MS Mincho", "Noto Serif CJK JP", "Yu Gothic", "Microsoft YaHei", "Noto Sans CJK JP"])
	_build_world()
	_build_figures()
	_build_bullets()
	_build_hud()
	_build_sound()
	var scene = rt.call(fn["scene"], [world])
	if scene != null:
		_take(scene)
		cam_pos = _cam_target()[0]
		cam_look = _cam_target()[1]


# --- a tick ---------------------------------------------------------------

func _physics_process(_delta):
	if rt == null or not rt.is_open():
		return
	if Input.is_physical_key_pressed(KEY_ESCAPE) and not demo:
		get_tree().quit()
	var held: Array = _bot() if demo else _keys()
	var hin = rt.call(fn["input"], held)
	var t0 := Time.get_ticks_usec()
	var next = rt.call(fn["tick"], [world, hin])
	if next == null:
		push_error("LOVA: the tick trapped: " + rt.error())
		rt.release([hin])
		set_physics_process(false)
		return
	tick_usec = Time.get_ticks_usec() - t0
	tick_steps = rt.steps()
	rt.release([world, hin])
	world = next
	var t1 := Time.get_ticks_usec()
	var scene = rt.call(fn["scene"], [world])
	scene_usec = Time.get_ticks_usec() - t1
	if scene == null:
		push_error("LOVA: scene trapped: " + rt.error())
		set_physics_process(false)
		return
	ticks += 1
	_take(scene)
	_events(hud_data[18])
	if smoke:
		if ticks % 60 == 0:
			print("smoke: tick %d  bullets %d  tick %d steps %.2f ms  scene %.2f ms" % [ticks, bullets.size() / 4, tick_steps, tick_usec / 1000.0, scene_usec / 1000.0])
		if ticks >= 600:
			print("smoke: ok")
			get_tree().quit()
	if shot_path != "" and ticks == shot_at:
		_take_shot()
	if movie_ticks > 0 and ticks >= movie_ticks:
		print("movie: ", ticks, " ticks")
		get_tree().quit()


func _exit_tree():
	if rt != null and rt.is_open():
		rt.close()


func _take(scene: Array):
	hud_data = scene[0]
	bullets = scene[1] if scene[1] != null else []
	shots = scene[2] if scene[2] != null else []


func _keys() -> Array:
	var k := func(a, b): return 1 if (Input.is_physical_key_pressed(a) or Input.is_physical_key_pressed(b)) else 0
	var mx: int = k.call(KEY_D, KEY_RIGHT) - k.call(KEY_A, KEY_LEFT)
	var mz: int = k.call(KEY_W, KEY_UP) - k.call(KEY_S, KEY_DOWN)
	var my: int = k.call(KEY_SPACE, KEY_E) - k.call(KEY_CTRL, KEY_Q)
	var focus: int = k.call(KEY_SHIFT, KEY_SHIFT)
	var shoot: int = 1 if (Input.is_physical_key_pressed(KEY_Z) or Input.is_physical_key_pressed(KEY_J) or Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT)) else 0
	var bomb: int = 1 if (Input.is_physical_key_pressed(KEY_X) or Input.is_physical_key_pressed(KEY_K) or Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT)) else 0
	var retry: int = k.call(KEY_R, KEY_R)
	return [mx, mz, my, focus, shoot, bomb, retry]


# Nobody at the keys: circle the witch, keep her in range, shoot, and
# lean away from whatever comes close -- each bullet within three metres
# pushes her away from it by the inverse square of its distance.  Good
# enough to be hit sometimes, which is what a demonstration should show.
func _bot() -> Array:
	if hud_data.size() < 23:
		return [0, 0, 0, 0, 1, 0, 0]
	var p := _v(hud_data, 0)
	var b := _v(hud_data, 3)
	var f := Vector3(hud_data[20] / 1024.0, 0, hud_data[21] / 1024.0)
	var r := Vector3(-f.z, 0, f.x)
	var push := Vector3.ZERO
	var nearest := INF
	for i in range(0, bullets.size(), 4):
		var q := Vector3(bullets[i] / F, bullets[i + 1] / F, bullets[i + 2] / F)
		var d := p - q
		var l := d.length()
		if l < 3.0 and l > 0.001:
			push += d / (l * l * l)
			nearest = min(nearest, l)
	var mx := 1 if (ticks / 300) % 2 == 0 else -1
	var mz := 0
	var my := 0
	var flat := Vector2(b.x - p.x, b.z - p.z).length()
	if flat < 7.0:
		mz = -1
	elif flat > 13.0:
		mz = 1
	var want_y := b.y + 1.5 * sin(ticks / 120.0)
	if p.y < want_y - 0.5:
		my = 1
	elif p.y > want_y + 0.5:
		my = -1
	if push.length() > 0.08:
		var pr := push.dot(r)
		var pf := push.dot(f)
		mx = 1 if pr > 0.04 else (-1 if pr < -0.04 else 0)
		mz = 1 if pf > 0.04 else (-1 if pf < -0.04 else mz)
		my = 1 if push.y > 0.04 else (-1 if push.y < -0.04 else my)
	var focus := 1 if nearest < 1.2 else 0
	var bomb := 1 if nearest < 0.35 and hud_data[7] > 0 and hud_data[15] == 0 and (ticks % 7 == 0) else 0
	var retry := 1 if hud_data[16] == 1 else 0
	return [mx, mz, my, focus, 1, bomb, retry]


static func _v(a: Array, i: int) -> Vector3:
	return Vector3(a[i] / F, a[i + 1] / F, a[i + 2] / F)


# --- what the rules said, drawn -------------------------------------------

func _process(delta):
	if hud_data.size() < 23:
		return
	var t := Time.get_ticks_msec() / 1000.0
	var p := _v(hud_data, 0)
	var b := _v(hud_data, 3)
	var f := Vector3(hud_data[20] / 1024.0, 0, hud_data[21] / 1024.0)
	var focus: bool = hud_data[22] == 1
	var safe: int = hud_data[15]

	maiden.position = p
	maiden.look_at(p + f, Vector3.UP)
	maiden.visible = safe == 0 or (ticks / 4) % 2 == 0
	hitbox.visible = focus or safe > 0
	graze_ring.visible = focus
	graze_ring.rotation.y = t * 2.0
	maiden_shadow.position = Vector3(p.x, 0.03, p.z)
	var toward_maiden := Vector3(p.x - b.x, 0, p.z - b.z).normalized()
	witch.position = b
	witch.look_at(b + toward_maiden, Vector3.UP)
	witch.rotation.z = 0.08 * sin(t * 1.3)
	witch_shadow.position = Vector3(b.x, 0.03, b.z)
	circle.position = b - toward_maiden * 1.2
	circle.look_at(circle.position - toward_maiden, Vector3.UP)
	circle.rotate_object_local(Vector3.FORWARD, t * 0.8)
	var sc := 1.0 + 0.05 * sin(t * 3.0)
	circle.scale = Vector3(sc, sc, sc)

	_draw_bullets(p, t)
	_draw_shots(b)
	_draw_bomb()

	var target := _cam_target()
	var k := 1.0 - pow(0.001, delta)
	cam_pos = cam_pos.lerp(target[0], k)
	cam_look = cam_look.lerp(target[1], k)
	var jolt := Vector3.ZERO
	if shake > 0.0:
		jolt = Vector3(randf_range(-1, 1), randf_range(-1, 1), randf_range(-1, 1)) * shake
		shake = max(0.0, shake - delta * 1.5)
	cam.position = cam_pos + jolt
	cam.look_at(cam_look, Vector3.UP)
	_draw_hud()


# The camera sits behind her and above, looking past her at a point
# between the two of them, so the witch stays in view and the maiden
# low in the frame.
func _cam_target() -> Array:
	var p := _v(hud_data, 0)
	var b := _v(hud_data, 3)
	var f := Vector3(hud_data[20] / 1024.0, 0, hud_data[21] / 1024.0)
	var pos := p - f * 4.2 + Vector3(0, 1.3, 0)
	var look := p.lerp(b, 0.45) + Vector3(0, 0.4, 0)
	return [pos, look]


func _draw_bullets(p: Vector3, t: float):
	var counts := [0, 0, 0]
	var n := bullets.size() / 4
	var spin := Basis(Vector3.UP, t * 4.0) * Basis(Vector3.RIGHT, t * 2.5)
	for i in range(n):
		var j := i * 4
		var kind: int = bullets[j + 3]
		var c: int = counts[kind]
		if c >= CAP:
			continue
		counts[kind] = c + 1
		var x: float = bullets[j] / F
		var y: float = bullets[j + 1] / F
		var z: float = bullets[j + 2] / F
		var d := Vector3(x, y, z).distance_to(p)
		var s: float = DRAW_R[kind] * (1.35 if d < 2.5 else 1.0)
		var col: Color = KIND_COLOR[kind]
		if kind == 1:
			col = Color.from_hsv(fmod(float(i) * 0.013 + t * 0.1, 1.0), 0.75, 1.0)
		if d < 2.5:
			col = col.lerp(Color.WHITE, 0.35)
		var buf: PackedFloat32Array = bufs[kind]
		var o := c * 16
		var bs: Basis = spin.scaled(Vector3(s, s, s)) if kind == 1 else Basis.from_scale(Vector3(s, s, s))
		buf[o] = bs.x.x; buf[o + 1] = bs.y.x; buf[o + 2] = bs.z.x; buf[o + 3] = x
		buf[o + 4] = bs.x.y; buf[o + 5] = bs.y.y; buf[o + 6] = bs.z.y; buf[o + 7] = y
		buf[o + 8] = bs.x.z; buf[o + 9] = bs.y.z; buf[o + 10] = bs.z.z; buf[o + 11] = z
		buf[o + 12] = col.r; buf[o + 13] = col.g; buf[o + 14] = col.b; buf[o + 15] = 1.0
		# its shadow on the ground, fainter the higher it flies
		if i < CAP:
			var so := i * 16
			var ss := s * 1.6
			var a: float = clamp(1.0 - y / 14.0, 0.15, 1.0) * 0.55
			shadow_buf[so] = ss; shadow_buf[so + 1] = 0; shadow_buf[so + 2] = 0; shadow_buf[so + 3] = x
			shadow_buf[so + 4] = 0; shadow_buf[so + 5] = 1; shadow_buf[so + 6] = 0; shadow_buf[so + 7] = 0.02
			shadow_buf[so + 8] = 0; shadow_buf[so + 9] = 0; shadow_buf[so + 10] = ss; shadow_buf[so + 11] = z
			shadow_buf[so + 12] = 0; shadow_buf[so + 13] = 0; shadow_buf[so + 14] = 0; shadow_buf[so + 15] = a
	for kind in range(3):
		mm[kind].buffer = bufs[kind]
		mm[kind].visible_instance_count = counts[kind]
	mm_shadow.buffer = shadow_buf
	mm_shadow.visible_instance_count = min(n, CAP)


func _draw_shots(b: Vector3):
	var n: int = min(shots.size() / 3, SHOT_CAP)
	for i in range(n):
		var at := Vector3(shots[i * 3] / F, shots[i * 3 + 1] / F, shots[i * 3 + 2] / F)
		var dir := (b - at).normalized()
		if dir.length() < 0.5:
			dir = Vector3.FORWARD
		var bs := Basis.looking_at(dir, Vector3.UP if absf(dir.y) < 0.95 else Vector3.RIGHT)
		var o := i * 16
		shot_buf[o] = bs.x.x; shot_buf[o + 1] = bs.y.x; shot_buf[o + 2] = bs.z.x; shot_buf[o + 3] = at.x
		shot_buf[o + 4] = bs.x.y; shot_buf[o + 5] = bs.y.y; shot_buf[o + 6] = bs.z.y; shot_buf[o + 7] = at.y
		shot_buf[o + 8] = bs.x.z; shot_buf[o + 9] = bs.y.z; shot_buf[o + 10] = bs.z.z; shot_buf[o + 11] = at.z
		shot_buf[o + 12] = 1.0; shot_buf[o + 13] = 0.9; shot_buf[o + 14] = 0.9; shot_buf[o + 15] = 1.0
	mm_shots.buffer = shot_buf
	mm_shots.visible_instance_count = n


# A bomb: seven orbs of light burst out from her and swell, the colours
# of a rainbow, for a second and a half.
func _draw_bomb():
	if bomb_t < 0:
		for o in bomb_orbs:
			o.visible = false
		return
	bomb_t += 1
	var u := bomb_t / 90.0
	var p := maiden.position
	for i in range(bomb_orbs.size()):
		var o: MeshInstance3D = bomb_orbs[i]
		o.visible = u < 1.0
		var ang := TAU * i / bomb_orbs.size() + u * 4.0
		var rad := 1.0 + u * 14.0
		o.position = p + Vector3(cos(ang) * rad, sin(u * 6.0 + i) * 1.5, sin(ang) * rad)
		var s := 0.6 + u * 3.5
		o.scale = Vector3(s, s, s)
		var m: StandardMaterial3D = o.material_override
		m.albedo_color.a = clamp(1.0 - u, 0.0, 1.0) * 0.6
	if u >= 1.0:
		bomb_t = -1


func _events(ev: int):
	if ev & 16:
		_play("shot", -16.0)
	if ev & 32 and ticks % 3 == 0:
		_play("struck", -18.0)
		witch_mat.emission_energy_multiplier = 1.5
	else:
		witch_mat.emission_energy_multiplier = max(0.0, witch_mat.emission_energy_multiplier - 0.2)
	if ev & 8 and ticks - last_graze_sfx > 3:
		last_graze_sfx = ticks
		_play("graze", -8.0)
	if ev & 1:
		_play("hit", -2.0)
		shake = 0.6
		bomb_t = -1
	if ev & 2:
		_play("bomb", -3.0)
		bomb_t = 0
		shake = 0.3
	# the card is declared on the tick it begins, not when the last one
	# ended: `k` reaches nought at the end of the pause
	var k: int = hud_data[13]
	if k == 0 and last_k != 0 and hud_data[17] == 0 and hud_data[16] == 0:
		var i: int = hud_data[10]
		_play("declare", -4.0)
		_banner(CARDS[i][0], CARDS[i][1])
	last_k = k
	if ev & 64:
		_play("declare", -2.0)
	if ev & 128:
		_play("hit", 0.0)


# --- the HUD ----------------------------------------------------------------

func _label(size: int, color: Color, outline := 6) -> Label:
	var l := Label.new()
	l.add_theme_font_override("font", font)
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	l.add_theme_color_override("font_outline_color", Color(0.05, 0.0, 0.1, 0.85))
	l.add_theme_constant_override("outline_size", outline)
	return l


func _build_hud():
	var layer := CanvasLayer.new()
	add_child(layer)
	hp_back = ColorRect.new()
	hp_back.color = Color(0, 0, 0, 0.45)
	hp_back.position = Vector2(200, 18)
	hp_back.size = Vector2(880, 10)
	layer.add_child(hp_back)
	hp_bar = ColorRect.new()
	hp_bar.color = Color(1.0, 0.35, 0.5)
	hp_bar.position = Vector2(200, 18)
	hp_bar.size = Vector2(880, 10)
	layer.add_child(hp_bar)
	boss_label = _label(18, Color(1, 0.95, 0.8))
	boss_label.position = Vector2(24, 10)
	layer.add_child(boss_label)
	timer_label = _label(30, Color(1, 1, 1))
	timer_label.position = Vector2(1170, 4)
	layer.add_child(timer_label)
	card_label = _label(26, Color(1, 0.92, 0.95))
	card_label.anchor_left = 1.0
	card_label.anchor_right = 1.0
	card_label.offset_left = -700
	card_label.offset_right = -24
	card_label.offset_top = 42
	card_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	layer.add_child(card_label)
	card_en = _label(15, Color(0.95, 0.85, 1.0, 0.9), 4)
	card_en.anchor_left = 1.0
	card_en.anchor_right = 1.0
	card_en.offset_left = -700
	card_en.offset_right = -24
	card_en.offset_top = 78
	card_en.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	layer.add_child(card_en)
	side_label = _label(20, Color(1, 1, 1))
	side_label.position = Vector2(24, 48)
	layer.add_child(side_label)
	readout = _label(14, Color(0.85, 1.0, 0.9, 0.85), 4)
	readout.anchor_top = 1.0
	readout.anchor_bottom = 1.0
	readout.offset_top = -30
	readout.offset_left = 24
	layer.add_child(readout)
	help_label = _label(13, Color(1, 1, 1, 0.7), 4)
	help_label.anchor_top = 1.0
	help_label.anchor_bottom = 1.0
	help_label.anchor_left = 1.0
	help_label.anchor_right = 1.0
	help_label.offset_top = -30
	help_label.offset_left = -760
	help_label.offset_right = -24
	help_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	help_label.text = "WASD move · Space/Ctrl up/down · Shift focus · Z shoot · X bomb · R retry"
	layer.add_child(help_label)
	banner = _label(40, Color(1, 0.9, 0.95), 10)
	banner.anchor_left = 0.0
	banner.anchor_right = 1.0
	banner.anchor_top = 0.33
	banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	layer.add_child(banner)
	banner_sub = _label(20, Color(1, 0.85, 1.0), 6)
	banner_sub.anchor_left = 0.0
	banner_sub.anchor_right = 1.0
	banner_sub.anchor_top = 0.33
	banner_sub.offset_top = 58
	banner_sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	layer.add_child(banner_sub)
	center_msg = _label(44, Color(1, 1, 1), 10)
	center_msg.anchor_left = 0.0
	center_msg.anchor_right = 1.0
	center_msg.anchor_top = 0.45
	center_msg.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	layer.add_child(center_msg)
	var fan := _label(12, Color(1, 1, 1, 0.55), 3)
	fan.position = Vector2(24, 694 - 34)
	fan.text = "東方Project 二次創作 · a fan game · rules in LOVA"
	layer.add_child(fan)


func _banner(jp: String, en: String):
	banner.text = jp
	banner_sub.text = "Spell Card Attack!!  " + en if jp != CARDS[0][0] else en
	banner_t = 150


func _draw_hud():
	var h := hud_data
	var i: int = h[10]
	var hp_max: int = max(1, h[12])
	var frac: float = clamp(float(h[11]) / hp_max, 0.0, 1.0)
	hp_bar.size.x = 880.0 * frac
	hp_bar.color = Color(1.0, 0.35, 0.5) if i > 0 else Color(0.95, 0.95, 1.0)
	boss_label.text = BOSS_NAME
	var k: int = h[13]
	var left: float = (h[14] - max(k, 0)) / 60.0
	timer_label.text = "%02d" % int(ceil(left)) if k >= 0 else ""
	timer_label.add_theme_color_override("font_color", Color(1, 0.3, 0.3) if left < 10.0 and k >= 0 else Color(1, 1, 1))
	card_label.text = CARDS[i][0]
	card_en.text = CARDS[i][1]
	var lives := ""
	for _n in range(max(0, h[6])):
		lives += "★"
	var bombs := ""
	for _n in range(max(0, h[7])):
		bombs += "✦"
	side_label.text = "Score  %s\nPlayer %s\nSpell  %s\nGraze  %d" % [_group(h[9]), lives, bombs, h[8]]
	readout.text = "LOVA  tick %s steps · %.2f ms   scene %.2f ms   bullets %d" % [_group(tick_steps), tick_usec / 1000.0, scene_usec / 1000.0, h[23]]
	if banner_t > 0:
		banner_t -= 1
		var a: float = clamp(banner_t / 30.0, 0.0, 1.0)
		banner.modulate.a = a
		banner_sub.modulate.a = a
	else:
		banner.text = ""
		banner_sub.text = ""
	if h[16] == 1:
		center_msg.text = "満身創痍  GAME OVER\nR to retry"
	elif h[17] == 1:
		center_msg.text = "CLEAR!!\n%s を撃破  Score %s\nR to play again" % [BOSS_NAME, _group(h[9])]
	elif k < 0 and i == 0 and h[19] < 80:
		center_msg.text = "東方天球譚\n〜 Celestial Sphere Duel 〜"
	else:
		center_msg.text = ""


static func _group(n: int) -> String:
	var s := str(n)
	var out := ""
	var count := 0
	for idx in range(s.length() - 1, -1, -1):
		out = s[idx] + out
		count += 1
		if count % 3 == 0 and idx > 0:
			out = "," + out
	return out


func _take_shot():
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	image.save_png(shot_path)
	print("shot: ", shot_path, " after ", ticks, " ticks; bullets ", bullets.size() / 4, "; last tick ", tick_steps, " steps, ", tick_usec, " us")
	get_tree().quit()


# --- the world ----------------------------------------------------------------

func _unshaded(color: Color, alpha := false) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = color
	if alpha:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	return m


func _lit(color: Color, rough := 0.8) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = rough
	return m


func _mesh(mesh: Mesh, mat: Material, parent: Node3D, at := Vector3.ZERO) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = mesh
	mi.material_override = mat
	mi.position = at
	parent.add_child(mi)
	return mi


func _build_world():
	var env := Environment.new()
	var sky := Sky.new()
	var sm := ProceduralSkyMaterial.new()
	sm.sky_top_color = Color(0.02, 0.02, 0.08)
	sm.sky_horizon_color = Color(0.32, 0.12, 0.3)
	sm.ground_horizon_color = Color(0.2, 0.08, 0.2)
	sm.ground_bottom_color = Color(0.02, 0.01, 0.04)
	sm.sky_energy_multiplier = 0.8
	sm.sun_angle_max = 20.0
	sky.sky_material = sm
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.55
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.glow_enabled = true
	env.glow_intensity = 0.7
	env.glow_strength = 1.0
	env.glow_bloom = 0.02
	env.glow_hdr_threshold = 1.0
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_ADDITIVE
	env.fog_enabled = true
	env.fog_light_color = Color(0.16, 0.08, 0.2)
	env.fog_density = 0.006
	env.fog_sky_affect = 0.0
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-35, -30, 0)
	sun.light_color = Color(1.0, 0.8, 0.7)
	sun.light_energy = 0.7
	add_child(sun)

	cam = Camera3D.new()
	cam.fov = 70
	cam.far = 400
	add_child(cam)
	cam.make_current()
	# a fill light that travels with the eye, so the two figures -- seen
	# from behind and against the night -- keep their colours
	var fill := OmniLight3D.new()
	fill.light_color = Color(1.0, 0.9, 0.95)
	fill.light_energy = 1.6
	fill.omni_range = 14.0
	fill.position = Vector3(0, 0.5, 0)
	cam.add_child(fill)

	# The moon, low and large behind the arena.
	var moon := _mesh(SphereMesh.new(), _unshaded(Color(1.4, 1.3, 1.1)), self, Vector3(-60, 55, -160))
	moon.scale = Vector3(14, 14, 14)

	# The ground far below the duel: a dark lake of light rings, the
	# arena's edge drawn on it at sixteen metres.
	var ground := PlaneMesh.new()
	ground.size = Vector2(400, 400)
	var gs := Shader.new()
	gs.code = """
shader_type spatial;
render_mode unshaded;
varying vec3 wp;
void vertex() { wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }
void fragment() {
	float r = length(wp.xz);
	float a = atan(wp.z, wp.x);
	vec3 base = mix(vec3(0.06, 0.04, 0.12), vec3(0.02, 0.01, 0.05), clamp(r / 120.0, 0.0, 1.0));
	float rings = smoothstep(0.06, 0.0, abs(fract(r / 4.0 + 0.5) - 0.5) * 4.0) * step(r, 16.0);
	float spokes = smoothstep(0.04, 0.0, abs(fract(a / 6.2831853 * 12.0 + 0.5) - 0.5)) * step(r, 16.0) * step(2.0, r);
	float edge = smoothstep(0.25, 0.0, abs(r - 16.0));
	vec3 c = base + vec3(0.25, 0.12, 0.35) * rings * 0.6 + vec3(0.2, 0.1, 0.3) * spokes * 0.35;
	c += vec3(1.6, 0.35, 0.45) * edge;
	ALBEDO = c;
}
"""
	var gm := ShaderMaterial.new()
	gm.shader = gs
	_mesh(ground, gm, self)

	# The edge in the air: a faint wall of light at sixteen metres,
	# banded, brighter where the camera looks along it.
	var wall := CylinderMesh.new()
	wall.top_radius = 16.0
	wall.bottom_radius = 16.0
	wall.height = 12.0
	wall.cap_top = false
	wall.cap_bottom = false
	wall.radial_segments = 96
	var ws := Shader.new()
	ws.code = """
shader_type spatial;
render_mode unshaded, blend_add, cull_disabled, depth_draw_never, fog_disabled;
varying vec3 wp;
void vertex() { wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }
void fragment() {
	float bands = smoothstep(0.08, 0.0, abs(fract(wp.y / 1.5) - 0.5) - 0.42);
	float rim = pow(1.0 - abs(dot(NORMAL, VIEW)), 3.0);
	float fade = 1.0 - clamp(wp.y / 12.0, 0.0, 1.0);
	ALBEDO = vec3(0.9, 0.25, 0.45) * (0.02 + bands * 0.06 + rim * 0.18) * fade;
}
"""
	var wm := ShaderMaterial.new()
	wm.shader = ws
	_mesh(wall, wm, self, Vector3(0, 6, 0))

	# A shrine gate beyond the edge, and cherry trees round it, so that
	# near and far can be told apart.
	_torii(Vector3(0, 0, -24), 0.0)
	_torii(Vector3(0, 0, 24), PI)
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	for n in range(26):
		var ang := TAU * n / 26.0 + rng.randf_range(-0.08, 0.08)
		if absf(sin(ang)) > 0.97:
			continue
		var rad := rng.randf_range(21.0, 34.0)
		_sakura(Vector3(cos(ang) * rad, 0, sin(ang) * rad), rng)
	for n in range(12):
		var ang := TAU * (n + 0.5) / 12.0
		_lantern(Vector3(cos(ang) * 18.5, 0, sin(ang) * 18.5))

	# Petals on the wind.
	var petals := CPUParticles3D.new()
	petals.amount = 400
	petals.lifetime = 12.0
	petals.preprocess = 12.0
	petals.emission_shape = CPUParticles3D.EMISSION_SHAPE_BOX
	petals.emission_box_extents = Vector3(30, 1, 30)
	petals.position = Vector3(0, 16, 0)
	petals.direction = Vector3(0.4, -1, 0.2)
	petals.spread = 25.0
	petals.initial_velocity_min = 0.8
	petals.initial_velocity_max = 1.6
	petals.gravity = Vector3(0, -0.15, 0)
	petals.angular_velocity_min = -180
	petals.angular_velocity_max = 180
	petals.scale_amount_min = 0.6
	petals.scale_amount_max = 1.2
	var pq := QuadMesh.new()
	pq.size = Vector2(0.12, 0.09)
	var pm := _unshaded(Color(1.0, 0.7, 0.82))
	pm.cull_mode = BaseMaterial3D.CULL_DISABLED
	pm.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	pq.material = pm
	petals.mesh = pq
	add_child(petals)


func _torii(at: Vector3, yaw: float):
	var g := Node3D.new()
	g.position = at
	g.rotation.y = yaw
	add_child(g)
	var red := _lit(Color(0.85, 0.12, 0.1), 0.6)
	var black := _lit(Color(0.08, 0.06, 0.06))
	for sx in [-2.2, 2.2]:
		var post := CylinderMesh.new()
		post.top_radius = 0.28
		post.bottom_radius = 0.32
		post.height = 7.0
		_mesh(post, red, g, Vector3(sx, 3.5, 0))
	var kasagi := BoxMesh.new()
	kasagi.size = Vector3(7.2, 0.45, 0.7)
	_mesh(kasagi, black, g, Vector3(0, 7.2, 0))
	var shimaki := BoxMesh.new()
	shimaki.size = Vector3(6.6, 0.4, 0.6)
	_mesh(shimaki, red, g, Vector3(0, 6.8, 0))
	var nuki := BoxMesh.new()
	nuki.size = Vector3(5.6, 0.32, 0.4)
	_mesh(nuki, red, g, Vector3(0, 5.6, 0))


func _sakura(at: Vector3, rng: RandomNumberGenerator):
	var g := Node3D.new()
	g.position = at
	g.rotation.y = rng.randf() * TAU
	var s := rng.randf_range(0.8, 1.3)
	g.scale = Vector3(s, s, s)
	add_child(g)
	var trunk := CylinderMesh.new()
	trunk.top_radius = 0.18
	trunk.bottom_radius = 0.32
	trunk.height = 3.2
	_mesh(trunk, _lit(Color(0.25, 0.14, 0.12)), g, Vector3(0, 1.6, 0))
	var pink := _lit(Color(1.0, 0.62, 0.78), 0.9)
	pink.emission_enabled = true
	pink.emission = Color(0.5, 0.15, 0.3)
	pink.emission_energy_multiplier = 0.4
	for n in range(5):
		var blob := SphereMesh.new()
		var r := rng.randf_range(1.1, 1.7)
		blob.radius = r
		blob.height = r * 1.6
		blob.radial_segments = 12
		blob.rings = 6
		_mesh(blob, pink, g, Vector3(rng.randf_range(-1.2, 1.2), 3.6 + rng.randf_range(-0.3, 0.9), rng.randf_range(-1.2, 1.2)))


func _lantern(at: Vector3):
	var g := Node3D.new()
	g.position = at
	add_child(g)
	var stone := _lit(Color(0.45, 0.43, 0.42))
	var base := CylinderMesh.new()
	base.top_radius = 0.15
	base.bottom_radius = 0.3
	base.height = 1.0
	_mesh(base, stone, g, Vector3(0, 0.5, 0))
	var box := BoxMesh.new()
	box.size = Vector3(0.5, 0.45, 0.5)
	_mesh(box, _unshaded(Color(1.8, 1.2, 0.5)), g, Vector3(0, 1.25, 0))
	var roof := CylinderMesh.new()
	roof.top_radius = 0.05
	roof.bottom_radius = 0.5
	roof.height = 0.35
	roof.radial_segments = 4
	_mesh(roof, stone, g, Vector3(0, 1.65, 0))


# --- the two figures, from primitives -------------------------------------

func _build_figures():
	# The shrine maiden: red and white, a great red bow, detached
	# sleeves.  Her hitbox -- the point the rules test -- is at her chest,
	# where the node's origin is.
	maiden = Node3D.new()
	add_child(maiden)
	var red := _lit(Color(0.85, 0.08, 0.12), 0.6)
	var white := _lit(Color(0.95, 0.95, 0.97), 0.7)
	var skin := _lit(Color(1.0, 0.86, 0.76))
	var hair := _lit(Color(0.12, 0.07, 0.06), 0.5)
	var skirt := CylinderMesh.new()
	skirt.top_radius = 0.12
	skirt.bottom_radius = 0.34
	skirt.height = 0.55
	_mesh(skirt, red, maiden, Vector3(0, -0.45, 0))
	var torso := CylinderMesh.new()
	torso.top_radius = 0.13
	torso.bottom_radius = 0.15
	torso.height = 0.4
	_mesh(torso, white, maiden, Vector3(0, 0.0, 0))
	var collar := BoxMesh.new()
	collar.size = Vector3(0.1, 0.12, 0.05)
	_mesh(collar, _lit(Color(1.0, 0.85, 0.2)), maiden, Vector3(0, 0.12, -0.15))
	var head := SphereMesh.new()
	head.radius = 0.16
	head.height = 0.32
	_mesh(head, skin, maiden, Vector3(0, 0.36, 0))
	var hairball := SphereMesh.new()
	hairball.radius = 0.19
	hairball.height = 0.36
	_mesh(hairball, hair, maiden, Vector3(0, 0.39, 0.04))
	var back_hair := BoxMesh.new()
	back_hair.size = Vector3(0.32, 0.45, 0.1)
	_mesh(back_hair, hair, maiden, Vector3(0, 0.18, 0.14))
	for sx in [-1.0, 1.0]:
		var lobe := PrismMesh.new()
		lobe.size = Vector3(0.36, 0.3, 0.08)
		var l := _mesh(lobe, red, maiden, Vector3(sx * 0.2, 0.6, 0.12))
		l.rotation.z = -sx * PI / 2
		var sleeve := CylinderMesh.new()
		sleeve.top_radius = 0.07
		sleeve.bottom_radius = 0.14
		sleeve.height = 0.38
		var s := _mesh(sleeve, white, maiden, Vector3(sx * 0.26, -0.04, 0))
		s.rotation.z = sx * 0.35
		var tube := SphereMesh.new()
		tube.radius = 0.035
		tube.height = 0.07
		_mesh(tube, _lit(Color(1.0, 0.85, 0.2)), maiden, Vector3(sx * 0.16, 0.36, -0.06))
	var knot := SphereMesh.new()
	knot.radius = 0.06
	knot.height = 0.12
	_mesh(knot, red, maiden, Vector3(0, 0.6, 0.12))
	# the hitbox: a bright dot inside a ring, drawn over everything
	var hb := SphereMesh.new()
	hb.radius = 0.1
	hb.height = 0.2
	var hbm := _unshaded(Color(1.6, 1.6, 1.6))
	hbm.no_depth_test = true
	hbm.render_priority = 10
	hitbox = _mesh(hb, hbm, maiden)
	var ring := TorusMesh.new()
	ring.inner_radius = 0.66
	ring.outer_radius = 0.7
	var rm := _unshaded(Color(0.6, 0.9, 1.2, 0.5), true)
	rm.no_depth_test = true
	graze_ring = _mesh(ring, rm, maiden)
	graze_ring.rotation.x = PI / 2
	var sh := CylinderMesh.new()
	sh.top_radius = 0.35
	sh.bottom_radius = 0.35
	sh.height = 0.01
	maiden_shadow = _mesh(sh, _unshaded(Color(0, 0, 0, 0.5), true), self)

	# The witch: black and white, a pointed hat with a broad brim, golden
	# hair, riding a broom.
	witch = Node3D.new()
	witch.scale = Vector3(1.7, 1.7, 1.7)
	add_child(witch)
	var black := _lit(Color(0.07, 0.06, 0.09), 0.6)
	witch_mat = black
	black.emission_enabled = true
	black.emission = Color(1.0, 0.6, 0.8)
	black.emission_energy_multiplier = 0.0
	var gold := _lit(Color(1.0, 0.82, 0.35), 0.5)
	var dress := CylinderMesh.new()
	dress.top_radius = 0.15
	dress.bottom_radius = 0.42
	dress.height = 0.7
	_mesh(dress, black, witch, Vector3(0, -0.4, 0))
	var apron := BoxMesh.new()
	apron.size = Vector3(0.34, 0.6, 0.04)
	_mesh(apron, white, witch, Vector3(0, -0.4, -0.3)).rotation.x = -0.35
	var body := CylinderMesh.new()
	body.top_radius = 0.14
	body.bottom_radius = 0.16
	body.height = 0.38
	_mesh(body, black, witch, Vector3(0, 0.1, 0))
	_mesh(head, skin, witch, Vector3(0, 0.45, 0))
	var blond := SphereMesh.new()
	blond.radius = 0.2
	blond.height = 0.38
	_mesh(blond, gold, witch, Vector3(0, 0.46, 0.05))
	var locks := BoxMesh.new()
	locks.size = Vector3(0.42, 0.5, 0.14)
	_mesh(locks, gold, witch, Vector3(0, 0.25, 0.1))
	var brim := CylinderMesh.new()
	brim.top_radius = 0.5
	brim.bottom_radius = 0.5
	brim.height = 0.03
	_mesh(brim, black, witch, Vector3(0, 0.6, 0))
	var cone := CylinderMesh.new()
	cone.top_radius = 0.0
	cone.bottom_radius = 0.22
	cone.height = 0.7
	var c := _mesh(cone, black, witch, Vector3(0, 0.95, 0.06))
	c.rotation.x = 0.25
	var band := CylinderMesh.new()
	band.top_radius = 0.215
	band.bottom_radius = 0.225
	band.height = 0.06
	_mesh(band, white, witch, Vector3(0, 0.65, 0.01))
	var stick := CylinderMesh.new()
	stick.top_radius = 0.03
	stick.bottom_radius = 0.03
	stick.height = 1.8
	var st := _mesh(stick, _lit(Color(0.45, 0.28, 0.12)), witch, Vector3(0, -0.55, 0.1))
	st.rotation.x = PI / 2
	var bristles := CylinderMesh.new()
	bristles.top_radius = 0.05
	bristles.bottom_radius = 0.2
	bristles.height = 0.5
	var br := _mesh(bristles, _lit(Color(0.75, 0.6, 0.3)), witch, Vector3(0, -0.55, 1.2))
	br.rotation.x = PI / 2
	var wsh := CylinderMesh.new()
	wsh.top_radius = 0.6
	wsh.bottom_radius = 0.6
	wsh.height = 0.01
	witch_shadow = _mesh(wsh, _unshaded(Color(0, 0, 0, 0.45), true), self)

	# Her magic circle, turning behind her: two rings and a star.
	var q := QuadMesh.new()
	q.size = Vector2(6.0, 6.0)
	var cs := Shader.new()
	cs.code = """
shader_type spatial;
render_mode unshaded, blend_add, cull_disabled, depth_draw_never, fog_disabled;
float seg(vec2 p, vec2 a, vec2 b) {
	vec2 pa = p - a, ba = b - a;
	float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
	return length(pa - ba * h);
}
void fragment() {
	vec2 p = (UV - 0.5) * 2.0;
	float r = length(p);
	float w = 0.012;
	float d = min(abs(r - 0.95), abs(r - 0.82));
	d = min(d, abs(r - 0.35));
	for (int i = 0; i < 5; i++) {
		float a0 = 6.2831853 * float(i) / 5.0 + 1.5707963;
		float a1 = 6.2831853 * float(i + 2) / 5.0 + 1.5707963;
		d = min(d, seg(p, 0.82 * vec2(cos(a0), sin(a0)), 0.82 * vec2(cos(a1), sin(a1))));
	}
	float line = smoothstep(w * 2.0, 0.0, d);
	float glow = smoothstep(0.12, 0.0, d) * 0.25;
	ALBEDO = vec3(1.0, 0.75, 0.3) * (line * 1.6 + glow) * step(r, 1.0);
}
"""
	var cm := ShaderMaterial.new()
	cm.shader = cs
	circle = _mesh(q, cm, self)

	for i in range(7):
		var orb := SphereMesh.new()
		orb.radius = 0.5
		orb.height = 1.0
		var col := Color.from_hsv(i / 7.0, 0.7, 1.0)
		var om := _unshaded(Color(col.r * 1.5, col.g * 1.5, col.b * 1.5, 0.6), true)
		om.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
		var o := _mesh(orb, om, self)
		o.visible = false
		bomb_orbs.append(o)


# --- the bullets ----------------------------------------------------------

func _bullet_material() -> ShaderMaterial:
	var s := Shader.new()
	s.code = """
shader_type spatial;
render_mode unshaded;
void fragment() {
	float f = 1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0);
	vec3 rim = COLOR.rgb * 1.8;
	ALBEDO = mix(vec3(1.3), rim, smoothstep(0.0, 0.3, f));
}
"""
	var m := ShaderMaterial.new()
	m.shader = s
	return m


func _star_mesh() -> ArrayMesh:
	# a five-pointed star, thick enough to read edge on
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var pts: Array[Vector2] = []
	for i in range(10):
		var r := 1.0 if i % 2 == 0 else 0.45
		var a := TAU * i / 10.0 + PI / 2
		pts.append(Vector2(cos(a), sin(a)) * r)
	var th := 0.3
	for i in range(10):
		var a := pts[i]
		var b := pts[(i + 1) % 10]
		for side in [1.0, -1.0]:
			var c := Vector3(0, 0, side * th)
			var n := Vector3(0, 0, side)
			st.set_normal(n); st.add_vertex(c)
			if side > 0:
				st.set_normal(n); st.add_vertex(Vector3(a.x, a.y, 0))
				st.set_normal(n); st.add_vertex(Vector3(b.x, b.y, 0))
			else:
				st.set_normal(n); st.add_vertex(Vector3(b.x, b.y, 0))
				st.set_normal(n); st.add_vertex(Vector3(a.x, a.y, 0))
	st.generate_normals()
	return st.commit()


func _build_bullets():
	var mat := _bullet_material()
	var sphere := SphereMesh.new()
	sphere.radius = 1.0
	sphere.height = 2.0
	sphere.radial_segments = 16
	sphere.rings = 8
	var meshes := [sphere, _star_mesh(), sphere]
	for kind in range(3):
		var m := MultiMesh.new()
		m.transform_format = MultiMesh.TRANSFORM_3D
		m.use_colors = true
		m.mesh = meshes[kind]
		m.instance_count = CAP
		m.visible_instance_count = 0
		var mi := MultiMeshInstance3D.new()
		mi.multimesh = m
		mi.material_override = mat
		add_child(mi)
		mm.append(m)
		var b := PackedFloat32Array()
		b.resize(CAP * 16)
		bufs.append(b)

	var disc := CylinderMesh.new()
	disc.top_radius = 1.0
	disc.bottom_radius = 1.0
	disc.height = 0.01
	disc.radial_segments = 12
	mm_shadow = MultiMesh.new()
	mm_shadow.transform_format = MultiMesh.TRANSFORM_3D
	mm_shadow.use_colors = true
	mm_shadow.mesh = disc
	mm_shadow.instance_count = CAP
	mm_shadow.visible_instance_count = 0
	var smi := MultiMeshInstance3D.new()
	smi.multimesh = mm_shadow
	var sm := StandardMaterial3D.new()
	sm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	sm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	sm.vertex_color_use_as_albedo = true
	smi.material_override = sm
	add_child(smi)
	shadow_buf.resize(CAP * 16)

	var amulet := BoxMesh.new()
	amulet.size = Vector3(0.12, 0.02, 0.42)
	mm_shots = MultiMesh.new()
	mm_shots.transform_format = MultiMesh.TRANSFORM_3D
	mm_shots.use_colors = true
	mm_shots.mesh = amulet
	mm_shots.instance_count = SHOT_CAP
	mm_shots.visible_instance_count = 0
	var ami := MultiMeshInstance3D.new()
	ami.multimesh = mm_shots
	var am := StandardMaterial3D.new()
	am.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	am.vertex_color_use_as_albedo = true
	am.albedo_color = Color(1.5, 1.2, 1.2)
	ami.material_override = am
	add_child(ami)
	shot_buf.resize(SHOT_CAP * 16)


# --- sound, synthesised -------------------------------------------------------

const RATE := 22050


func _wav(samples: PackedFloat32Array, loop := false) -> AudioStreamWAV:
	var data := PackedByteArray()
	data.resize(samples.size() * 2)
	for i in range(samples.size()):
		data.encode_s16(i * 2, int(clamp(samples[i], -1.0, 1.0) * 32000.0))
	var w := AudioStreamWAV.new()
	w.format = AudioStreamWAV.FORMAT_16_BITS
	w.mix_rate = RATE
	w.stereo = false
	w.data = data
	if loop:
		w.loop_mode = AudioStreamWAV.LOOP_FORWARD
		w.loop_end = samples.size()
	return w


func _tone(f0: float, f1: float, dur: float, noise := 0.0, square := 0.0) -> AudioStreamWAV:
	var n := int(dur * RATE)
	var s := PackedFloat32Array()
	s.resize(n)
	var ph := 0.0
	for i in range(n):
		var u := float(i) / n
		var f := lerpf(f0, f1, u)
		ph += TAU * f / RATE
		var v := sin(ph)
		if square > 0.0:
			v = lerpf(v, sign(v), square)
		v = lerpf(v, randf_range(-1, 1), noise)
		s[i] = v * pow(1.0 - u, 2.0) * 0.8
	return _wav(s)


func _build_sound():
	sfx["shot"] = _tone(1800, 900, 0.05, 0.6)
	sfx["struck"] = _tone(600, 300, 0.06, 0.3, 0.5)
	sfx["graze"] = _tone(3200, 2600, 0.05, 0.1)
	sfx["hit"] = _tone(900, 80, 0.6, 0.35, 0.6)
	sfx["bomb"] = _tone(120, 40, 1.2, 0.7)
	sfx["declare"] = _tone(440, 1760, 0.5, 0.0, 0.3)
	for i in range(10):
		var p := AudioStreamPlayer.new()
		add_child(p)
		players.append(p)
	music = AudioStreamPlayer.new()
	music.stream = _music()
	music.volume_db = -9.0
	add_child(music)
	if not smoke:
		music.play()


func _play(name: String, db: float):
	for p in players:
		if not p.playing:
			p.stream = sfx[name]
			p.volume_db = db
			p.play()
			return


# Eight bars in A minor at 150 a minute, written for this game: a lead
# in eighths over a pumping bass and an off-beat hat.  Not a tune of
# ZUN's -- a fan game may not take the music.
func _music() -> AudioStreamWAV:
	var lead := [69, 72, 76, 72, 74, 72, 71, 69,  65, 69, 72, 77, 76, 74, 72, 74,
				 67, 71, 74, 79, 77, 76, 74, 71,  76, 0, 74, 76, 79, 76, 74, 71,
				 81, 79, 76, 79, 81, 84, 83, 81,  77, 76, 77, 81, 79, 77, 76, 74,
				 74, 76, 79, 83, 81, 79, 77, 74,  76, 80, 83, 88, 83, 80, 76, 0]
	var bass := [45, 41, 43, 40, 45, 41, 43, 40]
	var eighth := 0.2
	var per := int(eighth * RATE)
	var n := per * lead.size()
	var s := PackedFloat32Array()
	s.resize(n)
	var ph_l := 0.0
	var ph_b := 0.0
	var seed := 12345
	for i in range(n):
		var e := i / per
		var u := float(i % per) / per
		var note: int = lead[e]
		var v := 0.0
		if note > 0:
			ph_l += TAU * 440.0 * pow(2.0, (note - 69) / 12.0) / RATE
			var sq := sin(ph_l)
			sq = lerpf(sq, sign(sq), 0.35) + 0.3 * sin(ph_l * 2.0)
			v += sq * 0.16 * (1.0 - u * 0.6)
		var root: int = bass[e / 8] + (12 if e % 2 == 1 else 0)
		ph_b += TAU * 440.0 * pow(2.0, (root - 69) / 12.0) / RATE
		var tri: float = 2.0 * absf(fmod(ph_b / TAU, 1.0) * 2.0 - 1.0) - 1.0
		v += tri * 0.22 * (1.0 - u * 0.5)
		if e % 2 == 1 and u < 0.25:
			seed = (seed * 1103515245 + 12345) & 0x7fffffff
			v += (float(seed % 2000) / 1000.0 - 1.0) * 0.05 * (1.0 - u * 4.0)
		if e % 4 == 0 and u < 0.3:
			v += sin(TAU * lerpf(110.0, 40.0, u / 0.3) * u * eighth) * 0.35 * (1.0 - u / 0.3)
		s[i] = v
	return _wav(s, true)
