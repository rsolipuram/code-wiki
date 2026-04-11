; Rust entities
(function_item name: (identifier) @entity.function)
(struct_item name: (type_identifier) @entity.class)
(trait_item name: (type_identifier) @entity.interface)
(impl_item (function_item name: (identifier) @entity.method))
(use_declaration) @entity.import
