package policy.room

default allow_room_access := false

# Verifica acesso direto pelo dispositivo
allow_room_access if {
	some emp in data.employees.result
	emp.full_name == input.full_name
	input.device in emp.devices
}

# Verifica acesso através de roles compartilhadas
allow_room_access if {
	some emp in data.employees.result
	some device in data.devices.result
	emp.full_name == input.full_name
	device.id == input.device # Corrigido para verificar pelo ID do dispositivo
	some role in emp.roles
	role in device.roles
}

# Bloqueia o acesso caso nenhuma das condições acima seja atendida
deny_room_access if {
	not allow_room_access
}
