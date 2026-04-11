; Python entities
(function_definition name: (identifier) @entity.function)
(class_definition name: (identifier) @entity.class)
(import_statement) @entity.import
(import_from_statement) @entity.import

; Decorated definitions — capture the inner name so the entity spans the decorator too
(decorated_definition
  definition: (function_definition name: (identifier) @entity.function))
(decorated_definition
  definition: (class_definition name: (identifier) @entity.class))
