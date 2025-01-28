package policy.room

default allow_room_access := false

# Verifica acesso direto pelo dispositivo ou através de roles
allow_room_access if {
	some emp in data.employees.result
	emp.full_name == input.full_name
	input.device in emp.devices # Acesso direto pelo dispositivo
}

allow_room_access if {
	some emp in data.employees.result
	some device in data.devices.result
	emp.full_name == input.full_name
	device.id == input.device
	some role in emp.roles
	role in device.roles # Acesso através de role compartilhada
}

deny_room_access if {
	not allow_room_access
}
