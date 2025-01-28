package access

import future.keywords.in

# Valor padrão para `allow`
default allow := false

# Permitir acesso se o dispositivo estiver na lista de dispositivos do funcionário
allow_device if {
	some emp in data.employees
	emp.id == input.user_id

	some device in data.devices
	device.id == input.device_id
	device.id in emp.devices
}

allow_role if {
	some emp in data.employees
	emp.id == input.user_id

	some device in data.devices
	device.id == input.device_id

	some r in emp.roles
	r in device.roles
}

allow if {
	allow_device
}

allow if {
	allow_role
}
