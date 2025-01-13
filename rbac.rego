package policy

import rego.v1

# Regras de RBAC
default allow := false

allow if {
	some emp in data.employees
	emp.full_name == input.full_name
	emp.is_superuser == true
}

allow if {
	some emp in data.employees
	emp.full_name == input.full_name
	emp.is_staff == true
	some action in input.allowed_actions
	input.allowed_actions[action] == "read"
}

deny if {
	not allow
}
