package employees

# Regras de RBAC
default allow = false

allow if {
    input.is_superuser == true
}

allow if {
    input.is_staff == true
    input.allowed_actions[_] == "read"
}

deny if {
    input.is_staff == true
    not allow
}

# Função utilitária
hasPermission(grants, roles) if {
    some i
    grants[i] == roles[i]
}
