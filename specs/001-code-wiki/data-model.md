# Data Model: Code Wiki Platform

**Date**: 2026-02-15
**Feature**: AI-Powered Code Wiki Platform
**Source**: Derived from [spec.md](./spec.md) Key Entities

---

## Entity Relationships

```
Repository (1) ──< (N) Wiki
Wiki (1) ──< (N) WikiPage
Wiki (1) ──< (N) Module
Module (1) ──< (N) CodeEntity
CodeEntity (N) ──< (N) CodeEntity (relationships)
Repository (1) ──< (N) UpdateEvent
User (N) ──< (N) Repository (access)
User (1) ──< (N) ChatConversation
```

---

## MVP Scope Note

**MVP (Phase 1)** includes entities 1-7:
- Repository, Wiki, WikiPage, Module, CodeEntity, ChatConversation, UpdateEvent

**Phase 2** (future) includes entities 8-9:
- User, RepositoryAccess (authentication and private repo support)

**MVP operates without authentication** - all repositories are public, no user accounts needed.

---

## 1. Repository

Represents a code repository being analyzed and documented.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique identifier |
| `url` | String | REQUIRED, UNIQUE | Repository URL (GitHub, GitLab, etc.) |
| `name` | String | REQUIRED | Repository name |
| `owner` | String | REQUIRED | Repository owner/organization |
| `primary_languages` | String[] | REQUIRED | Detected languages (e.g., ["Python", "JavaScript"]) |
| `size_lines` | Integer | REQUIRED | Total lines of code |
| `size_files` | Integer | REQUIRED | Total number of files |
| `last_analyzed_commit` | String | REQUIRED | SHA of last analyzed commit |
| `last_analyzed_at` | Timestamp | REQUIRED | When analysis completed |
| `status` | Enum | REQUIRED | `pending`, `analyzing`, `ready`, `error` |
| `access_level` | Enum | REQUIRED | `public`, `private` |
| `created_at` | Timestamp | REQUIRED | When repository was added |
| `updated_at` | Timestamp | REQUIRED | Last modification |

### Validation Rules

- `url` must be valid Git repository URL
- `status` transitions: `pending` → `analyzing` → `ready` OR `error`
- `last_analyzed_commit` must exist in repository
- `primary_languages` must be from supported list (initially: Python, JavaScript, TypeScript)

### Relationships

- **Has one** Wiki
- **Has many** UpdateEvents
- **Accessed by many** Users

---

## 2. Wiki

The complete documentation structure for a repository.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique identifier |
| `repository_id` | UUID | FOREIGN KEY | Parent repository |
| `home_page_id` | UUID | FOREIGN KEY (WikiPage) | Home page reference |
| `structure_version` | Integer | REQUIRED | Incremental version of wiki structure |
| `module_count` | Integer | REQUIRED | Number of detected modules |
| `page_count` | Integer | REQUIRED | Total wiki pages |
| `status` | Enum | REQUIRED | `generating`, `ready`, `updating` |
| `generated_at` | Timestamp | REQUIRED | When wiki was generated |
| `updated_at` | Timestamp | REQUIRED | Last update |

### Validation Rules

- `home_page_id` must reference existing WikiPage
- `module_count` should be 3-10 for well-structured codebases
- `status` transitions with Repository status

### Relationships

- **Belongs to one** Repository
- **Has many** WikiPages
- **Has many** Modules

---

## 3. WikiPage

A structured documentation page within the wiki.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique identifier |
| `wiki_id` | UUID | FOREIGN KEY | Parent wiki |
| `page_type` | Enum | REQUIRED | `home`, `module`, `getting_started`, `function_index`, `glossary`, `api_reference` |
| `title` | String | REQUIRED | Page title |
| `slug` | String | REQUIRED, UNIQUE (per wiki) | URL-friendly identifier |
| `content` | JSONB | REQUIRED | Structured page content (sections) |
| `related_page_ids` | UUID[] | OPTIONAL | Links to related pages |
| `source_files` | String[] | OPTIONAL | Source code files referenced |
| `commit_hash` | String | REQUIRED | Commit this page represents |
| `created_at` | Timestamp | REQUIRED | Page creation |
| `updated_at` | Timestamp | REQUIRED | Last modification |

### Content Structure (JSONB)

```json
{
  "sections": [
    {
      "title": "Overview",
      "content": "Markdown text...",
      "type": "text"
    },
    {
      "title": "Location",
      "content": ["src/auth/login.py", "src/auth/session.py"],
      "type": "file_list"
    },
    {
      "title": "Key Components",
      "content": [
        {
          "name": "authenticate_user",
          "type": "function",
          "location": "src/auth/login.py:45",
          "signature": "authenticate_user(username: str, password: str) -> User | None"
        }
      ],
      "type": "component_list"
    },
    {
      "title": "Dependencies",
      "content": {
        "uses": ["database", "crypto"],
        "used_by": ["api_routes", "user_management"]
      },
      "type": "dependencies"
    }
  ]
}
```

### Validation Rules

- `slug` must be URL-safe (lowercase, hyphens only)
- `content` must have at least one section
- `commit_hash` must match Repository's `last_analyzed_commit` or earlier
- Module pages must include sections: Overview, Location, Dependencies

### Relationships

- **Belongs to one** Wiki
- **May reference many** WikiPages (related pages)
- **May reference one** Module (for module-type pages)

---

## 4. Module

A logical grouping of related code files (system/component).

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique identifier |
| `wiki_id` | UUID | FOREIGN KEY | Parent wiki |
| `wiki_page_id` | UUID | FOREIGN KEY (WikiPage) | Associated wiki page |
| `name` | String | REQUIRED | Module name (e.g., "Authentication System") |
| `slug` | String | REQUIRED, UNIQUE (per wiki) | URL-friendly identifier |
| `file_paths` | String[] | REQUIRED | Files in this module |
| `file_count` | Integer | REQUIRED | Number of files |
| `line_count` | Integer | REQUIRED | Total lines of code |
| `description` | Text | REQUIRED | AI-generated module description |
| `detection_confidence` | Float | REQUIRED | 0.0-1.0, how confident the auto-detection was |
| `dependencies_module_ids` | UUID[] | OPTIONAL | Modules this depends on |
| `created_at` | Timestamp | REQUIRED | Module detection time |

### Validation Rules

- `file_paths` must exist in Repository
- `detection_confidence` >= 0.5 for auto-approved modules
- `detection_confidence` < 0.5 flags module for review
- `dependencies_module_ids` must reference existing Modules

### Relationships

- **Belongs to one** Wiki
- **Has one** WikiPage (module documentation)
- **Has many** CodeEntities
- **Depends on many** Modules
- **Is depended on by many** Modules

---

## 5. CodeEntity

Represents a parseable element of code (function, class, module, file).

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique identifier |
| `module_id` | UUID | FOREIGN KEY | Parent module |
| `entity_type` | Enum | REQUIRED | `function`, `class`, `method`, `module`, `file`, `variable` |
| `name` | String | REQUIRED | Entity name |
| `qualified_name` | String | REQUIRED | Fully qualified name (e.g., "auth.login.authenticate_user") |
| `file_path` | String | REQUIRED | Source file location |
| `line_number` | Integer | REQUIRED | Starting line number |
| `signature` | String | OPTIONAL | Function/method signature |
| `description` | Text | OPTIONAL | AI-generated description |
| `docstring` | Text | OPTIONAL | Extracted docstring |
| `visibility` | Enum | REQUIRED | `public`, `private`, `protected` |
| `metadata` | JSONB | OPTIONAL | Language-specific metadata (types, decorators, etc.) |

### Relationships (Graph Database)

Stored in Neo4j with relationship types:

- `CALLS` → other CodeEntity (function calls)
- `IMPORTS` → other CodeEntity (module imports)
- `INHERITS_FROM` → other CodeEntity (class inheritance)
- `DEFINES` → other CodeEntity (class defines method)
- `USES` → other CodeEntity (variable usage)
- `OVERRIDES` → other CodeEntity (method override)

### Validation Rules

- `qualified_name` must be unique within Repository
- `file_path` must exist in Module's `file_paths`
- `line_number` must be > 0

---

## 6. ChatConversation

User interaction with AI assistant about a repository.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique identifier |
| `user_id` | UUID | FOREIGN KEY | User who owns conversation |
| `repository_id` | UUID | FOREIGN KEY | Repository being discussed |
| `messages` | JSONB[] | REQUIRED | Conversation history |
| `created_at` | Timestamp | REQUIRED | Conversation start |
| `updated_at` | Timestamp | REQUIRED | Last message |

### Message Structure (JSONB)

```json
{
  "role": "user" | "assistant",
  "content": "Message text",
  "timestamp": "2026-02-15T10:30:00Z",
  "references": [
    {
      "type": "wiki_page" | "code_entity" | "file",
      "id": "uuid-or-path",
      "title": "Display text"
    }
  ]
}
```

### Relationships

- **Belongs to one** User
- **References one** Repository

---

## 7. UpdateEvent

Represents a commit or code change that triggers wiki regeneration.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique identifier |
| `repository_id` | UUID | FOREIGN KEY | Repository being updated |
| `commit_hash` | String | REQUIRED | Git commit SHA |
| `changed_files` | String[] | REQUIRED | Files modified in commit |
| `affected_module_ids` | UUID[] | REQUIRED | Modules needing regeneration |
| `status` | Enum | REQUIRED | `pending`, `processing`, `completed`, `failed` |
| `started_at` | Timestamp | OPTIONAL | Processing start time |
| `completed_at` | Timestamp | OPTIONAL | Processing completion time |
| `error_message` | Text | OPTIONAL | Error details if failed |

### Validation Rules

- `status` transitions: `pending` → `processing` → `completed` OR `failed`
- `changed_files` must be subset of Repository files
- `affected_module_ids` must exist in Repository's Wiki

### Relationships

- **Belongs to one** Repository
- **Affects many** Modules

---

## 8. User

Represents a platform user.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PRIMARY KEY | Unique identifier |
| `email` | String | REQUIRED, UNIQUE | User email |
| `name` | String | REQUIRED | Display name |
| `auth_provider` | Enum | REQUIRED | `github`, `gitlab`, `email` |
| `auth_provider_id` | String | REQUIRED | External provider ID |
| `created_at` | Timestamp | REQUIRED | Account creation |
| `last_login_at` | Timestamp | OPTIONAL | Last login time |

### Relationships

- **Has access to many** Repositories
- **Has many** ChatConversations

---

## 9. RepositoryAccess (Join Table)

Controls user access to repositories.

### Fields

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `user_id` | UUID | FOREIGN KEY | User being granted access |
| `repository_id` | UUID | FOREIGN KEY | Repository being accessed |
| `access_level` | Enum | REQUIRED | `read`, `write`, `admin` |
| `granted_at` | Timestamp | REQUIRED | When access was granted |

**PRIMARY KEY**: (`user_id`, `repository_id`)

---

## Database Schema Notes

### PostgreSQL Tables

- `users`
- `repositories`
- `wikis`
- `wiki_pages`
- `modules`
- `chat_conversations`
- `update_events`
- `repository_access`

### Neo4j Graph

- `code_entities` (nodes with properties matching CodeEntity model)
- Relationships: `CALLS`, `IMPORTS`, `INHERITS_FROM`, `DEFINES`, `USES`, `OVERRIDES`

### pgvector

- Embeddings for WikiPages (semantic search)
- Embeddings for CodeEntities (semantic code search)
- Stored as `vector(1536)` columns in respective tables

---

## State Transitions

### Repository Status

```
pending → analyzing → ready
   ↓         ↓
 error ← ← ← ←
```

### Wiki Status

```
generating → ready
     ↓         ↓
   error ← updating → ready
```

### UpdateEvent Status

```
pending → processing → completed
             ↓
          failed
```

---

## Indexes

**PostgreSQL**:
- `repositories(url)` - UNIQUE
- `repositories(status)` - For finding repos to analyze
- `wiki_pages(wiki_id, slug)` - UNIQUE, for page lookup
- `modules(wiki_id, slug)` - UNIQUE, for module lookup
- `code_entities(module_id)` - For module code listing
- `update_events(repository_id, status)` - For pending updates

**Neo4j**:
- `CodeEntity(qualified_name)` - UNIQUE
- `CodeEntity(module_id)` - For module queries

---

**Data Model Complete**: 2026-02-15
**Ready for API Contracts**: ✅
