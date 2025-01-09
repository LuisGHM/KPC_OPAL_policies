package app.rbac

default allow = false

allow {
    some role
    input.user in roles[role].users
    input.action in roles[role].actions
    input.object in roles[role].objects
}

roles = {
    "admin": {
        "users": [u | data.employees[_].is_superuser == true; u = data.employees[_].full_name],
        "actions": ["create", "read", "update", "delete"],
        "objects": ["*"]
    },
    "employee": {
        "users": [u | data.employees[_].is_staff == true; u = data.employees[_].full_name],
        "actions": ["read"],
        "objects": ["finance"]
    }
}
