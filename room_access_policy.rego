package access

import future.keywords.in

default allow := false

# Regra que permite quando o dispositivo está na lista de dispositivos do usuário
allow if {
	some user in data.users.result
	user.id == input.user_id

	some device in data.devices.result
	device.id == input.device_id

	device.id in user.devices
}

# Regra que permite quando há ao menos uma role em comum entre usuário e dispositivo
allow if {
	some user in data.users.result
	user.id == input.user_id

	some device in data.devices.result
	device.id == input.device_id

	some r in user.roles
	r in device.roles
}
