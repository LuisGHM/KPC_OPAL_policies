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
        "users": ["alice"],
        "actions": ["create", "read", "update", "delete"],
        "objects": ["*"]
    },
    "employee": {
        "users": ["bob"],
        "actions": ["read"],
        "objects": ["finance"]
    }
}
