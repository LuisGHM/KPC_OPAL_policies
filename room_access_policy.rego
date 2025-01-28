package access

import future.keywords.in

default allow := false

# Regra que permite quando o device está na lista de devices do usuário
allow {
    some user in data.users
    user.id == input.user_id

    some device in data.devices
    device.id == input.device_id

    device.id in user.devices
}

# Regra que permite quando há ao menos uma role em comum entre usuário e dispositivo
allow {
    some user in data.users
    user.id == input.user_id

    some device in data.devices
    device.id == input.device_id

    some r in user.roles
    r in device.roles
}

# Define explicitamente os resultados finais
result := "Liberado" if allow
result := "Negado" if not allow
