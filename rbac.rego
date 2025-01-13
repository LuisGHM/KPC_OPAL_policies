package policy

import future.keywords.if

# Regras de RBAC
default allow = false

allow if {
	some e
	e := data.employees[_]
	e.full_name == input.full_name
	e.is_superuser == true
}

allow if {
	some e
	e := data.employees[_]
	e.full_name == input.full_name
	e.is_staff == true
	some action
	input.allowed_actions[action] == "read"
}

deny if {
	not allow
}
