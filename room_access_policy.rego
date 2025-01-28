package access

import future.keywords.in

# Valor padrão para `allow`
default allow := false

# Permitir acesso com base nos dispositivos
allow if {
    some emp in data.employees
    emp.id == input.user_id

    some device in data.devices
    device.id == input.device_id
    device.id in emp.devices
}

# Permitir acesso com base nos papéis
allow if {
    some emp in data.employees
    emp.id == input.user_id

    some device in data.devices
    device.id == input.device_id

    some r in emp.roles
    r in device.roles
}
