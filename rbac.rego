# rbac.rego
package rbac

default allow = false

allow {
  input.is_superuser
}

allow {
  input.is_staff
  # ...
}

deny {
  # ...
}
