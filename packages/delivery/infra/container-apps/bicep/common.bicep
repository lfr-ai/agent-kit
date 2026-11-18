// Shared offline validation helpers; compile-time imports only, no resources.

@export()
func onlyChars(value string, alphabet string) bool =>
  empty(filter(range(0, length(value)), i => !contains(alphabet, substring(value, i, 1))))

// Each '*' segment must be non-empty; every other segment must match exactly (case-sensitive).
@export()
func matchesId(value string, pattern string) bool =>
  length(split(value, '/')) == length(split(pattern, '/'))
    ? empty(filter(
        range(0, length(split(pattern, '/'))),
        i =>
          split(pattern, '/')[i] == '*' ? empty(split(value, '/')[i]) : split(value, '/')[i] != split(pattern, '/')[i]
      ))
    : false

func isDnsLabel(label string) bool =>
  length(label) >= 1 && length(label) <= 63 && !startsWith(label, '-') && !endsWith(label, '-') && onlyChars(
    label,
    'abcdefghijklmnopqrstuvwxyz0123456789-'
  )

@export()
func isHostName(value string) bool =>
  length(value) <= 253 && contains(value, '.') && empty(filter(split(value, '.'), label => !isDnsLabel(label)))
