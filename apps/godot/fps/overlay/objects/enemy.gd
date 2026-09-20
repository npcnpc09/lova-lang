extends Node3D

# The kit's enemy.gd with its rules taken out: the hover, the look at
# the player, the timer and the five-metre ray run in lib/fps.lova.
# What stays is the picture and the sounds -- where the node stands
# and which way it faces, the muzzle flashes on a hit, the hurt and
# destroy sounds -- applied by the player script once a tick from what
# the rules answer.

@export var player: Node3D

@onready var muzzle_a = $MuzzleA
@onready var muzzle_b = $MuzzleB

var health := 100
var alive := true


func _ready():
	add_to_group("lova_enemies")
	$Timer.stop()


# Where the rules put it this tick, whether it stands, what health it
# has, and whether its shot hit the player.
func apply(at: Vector3, is_alive: bool, hp: int, hit_player: bool):
	if is_alive:
		position = at
		if player:
			look_at(player.position + Vector3(0, 0.5, 0), Vector3.UP, true)
	if is_alive and hp < health:
		Audio.play("sounds/enemy_hurt.ogg")
	if alive and not is_alive:
		Audio.play("sounds/enemy_destroy.ogg")
		visible = false
	if is_alive and hit_player:
		muzzle_a.frame = 0
		muzzle_a.play("default")
		muzzle_a.rotation_degrees.z = randf_range(-45, 45)
		muzzle_b.frame = 0
		muzzle_b.play("default")
		muzzle_b.rotation_degrees.z = randf_range(-45, 45)
		Audio.play("sounds/enemy_attack.ogg")
	health = hp
	alive = is_alive


# A new game: the rules make the enemies again, so the node comes back.
func reset():
	health = 100
	alive = true
	visible = true


func _on_timer_timeout():
	pass
