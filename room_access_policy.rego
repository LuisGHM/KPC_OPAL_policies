package access

import future.keywords.in

# Para este exemplo, assume-se que em data.users temos o array de usuários
# e em data.devices temos o array de dispositivos, como foi fornecido no enunciado.

default allow := false

# Regra que permite quando o device está na lista de devices do usuário
allow if {
	some user in data.users
	user.id == input.user_id

	some device in data.devices
	device.id == input.device_id

	device.id in user.devices
}

# Regra que permite quando há ao menos uma role em comum entre usuário e dispositivo
allow if {
	some user in data.users
	user.id == input.user_id

	some device in data.devices
	device.id == input.device_id

	some r in user.roles
	r in device.roles
}

# Resultado final como "Liberado" se allow == true, senão "Negado".
result := "Liberado" if allow

result := "Negado" if not allow
