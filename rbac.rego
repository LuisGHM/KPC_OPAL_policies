package employees

# Regras de RBAC
default allow = false

allow {
	input.is_superuser == true
}

allow {
	input.is_staff == true
	input.allowed_actions[_] == "read"
}

deny {
	input.is_staff == true
	not allow
}

# Função utilitária
hasPermission(grants, roles) {
	some i
	grants[i] == roles[i]
}
