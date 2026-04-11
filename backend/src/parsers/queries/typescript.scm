; TypeScript / JavaScript entities
(function_declaration name: (identifier) @entity.function)
(method_definition name: (property_identifier) @entity.method)
(class_declaration name: (type_identifier) @entity.class)
(import_statement) @entity.import

; Interfaces and type aliases — map to "interface" entity type
(interface_declaration name: (type_identifier) @entity.interface)
(type_alias_declaration name: (type_identifier) @entity.interface)

; Enums — map to "class" entity type (close enough for graph purposes)
(enum_declaration name: (identifier) @entity.class)
