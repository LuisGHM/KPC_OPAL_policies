package access

import future.keywords.in

default allow := false

# Permitir acesso se o dispositivo estiver na lista de dispositivos do usuário
allow if {
	some user in data.users.result
	user.id == input.user_id

	some device in data.devices.result
	device.id == input.device_id

	device.id in user.devices
}

# Permitir acesso se houver ao menos uma role em comum entre o usuário e o dispositivo
allow if {
	some user in data.users.result
	user.id == input.user_id

	some device in data.devices.result
	device.id == input.device_id

	some r in user.roles
	r in device.roles
}
