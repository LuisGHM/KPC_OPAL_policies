package app.rbac

default allow = false

allow {
    some role
    input.user == roles[role].users[_]
    input.action == roles[role].actions[_]
    input.object == roles[role].objects[_]
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
