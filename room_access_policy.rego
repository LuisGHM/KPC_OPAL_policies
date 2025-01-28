package access

import future.keywords.in

# Valor padrão para `allow`
default allow := false

# Permitir acesso se o dispositivo estiver na lista de dispositivos do funcionário
allow if {
	some emp in data.employees
	emp.id == input.user_id

	some device in data.devices
	device.id == input.device_id
	device.id in emp.devices
}

# Permitir acesso se houver ao menos uma role em comum entre o funcionário e o dispositivo
allow if {
	some emp in data.employees
	emp.id == input.user_id

	some device in data.devices
	device.id == input.device_id

	some r in emp.roles
	r in device.roles
}
