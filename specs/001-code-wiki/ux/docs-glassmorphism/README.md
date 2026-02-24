# Code Wiki - Glassmorphism Design System Mockups

Production-grade HTML mockups for all Code Wiki pages with comprehensive mobile responsiveness.

## Architecture Decision

The wiki reading experience is unified into a single 3-column layout (`module.html`) where sidebar navigation replaces separate page routes. This matches modern documentation patterns (Stripe Docs, Tailwind, Mintlify).

**Removed pages** (absorbed into `module.html` sidebar sections):
- `home.html` → "Overview" sidebar section
- `getting-started.html` → "Getting Started" sidebar group
- `glossary.html` → "Reference > Glossary" sidebar item
- `api-reference.html` → "Reference > API" sidebar item
- `diagrams.html` → "Architecture > Diagrams" sidebar item
- `index.html` → Navigation hub (unnecessary with sidebar)

## Pages (9 remaining)

### 1. **module.html** - Wiki Reader (Primary)
**Purpose:** The unified wiki reading experience — all documentation content lives here

**Features:**
- Three-column layout (left nav, main content, right TOC)
- Sidebar navigation drives content sections (Overview, Modules, Getting Started, Glossary, API Reference, Diagrams)
- Breadcrumb navigation
- Author card with metadata
- Structured content sections (How It Works, Code Parsing, Module Detection, etc.)
- Syntax-highlighted code blocks
- Info boxes for key insights
- Interactive table of contents with scroll spy
- Smooth scrolling navigation

**Mobile Breakpoints:**
- 1400px: Hides right sidebar (TOC)
- 900px: Hides left sidebar, adds hamburger menu
- Mobile-first navigation with collapsible sidebar

---

### 2. **function.html** - Entity Detail Drill-Down
**Purpose:** In-depth documentation for individual functions/classes (reached via wiki links)

**Features:**
- Function signature with syntax highlighting
- Parameters table (name, type, description, required)
- Return value documentation
- Multiple usage examples with copy buttons
- "Called By" and "Calls" relationship sections with cards
- Source code preview with GitHub link
- Same 3-column layout as wiki reader

**Mobile Breakpoints:**
- 900px: Single-column layout, mobile menu toggle
- 480px: Smaller fonts, stacked metadata

---

### 3. **search.html** - Full-Text Search
**Purpose:** Search interface with filtering and results

**Features:**
- Prominent search bar with icon
- Tab filters (All, Functions, Classes, Modules, Documentation)
- Left sidebar with type/module/visibility filters
- Result cards with type badges, highlighted terms, code previews
- Sort options (Relevance, Name, Module, Recently Updated)

---

### 4. **chat.html** - AI Chat Assistant
**Purpose:** Conversational AI assistant for codebase questions

**Features:**
- Full-height chat layout
- Code blocks with syntax highlighting and copy buttons
- Link cards to related documentation
- Suggested follow-up questions
- Auto-resizing textarea input

---

### 5. **dashboard.html** - Repository Management
**Purpose:** Repository list and management interface

---

### 6. **submit.html** - Add Repository
**Purpose:** Add repository form with live URL validation and provider detection

---

### 7. **progress.html** - Analysis Pipeline
**Purpose:** Animated analysis pipeline with live stats and completion celebration

---

### 8. **login.html** - Authentication
**Purpose:** OAuth + email auth flow

---

### 9. **error.html** - Error States
**Purpose:** 404, analysis failure, private repo auth fallback

---

## Design System

### Colors
```css
--primary: #8B5CF6 (Purple)
--primary-light: #A78BFA
--secondary: #06B6D4 (Cyan)
--accent: #EC4899 (Pink)
--bg-dark: #0A0A0F
--bg-darker: #050508
--glass-bg: rgba(15, 15, 25, 0.7)
--glass-border: rgba(255, 255, 255, 0.1)
--text-primary: #F9FAFB
--text-secondary: #D1D5DB
--text-tertiary: #9CA3AF
```

### Typography
- **Body:** Outfit (Google Fonts)
- **Code:** Fira Code (Google Fonts)
- **Base Size:** 16px
- **Line Height:** 1.7

### Glass Cards
```css
background: var(--glass-bg);
backdrop-filter: blur(20px);
border: 1px solid var(--glass-border);
border-radius: 20px;
box-shadow: 0 8px 32px rgba(0, 0, 0, 0.37);
```

## File Structure
```
docs-glassmorphism/
├── module.html        # Wiki reader (primary — all wiki content)
├── function.html      # Entity detail drill-down
├── search.html        # Search results
├── chat.html          # AI chat interface
├── dashboard.html     # Repository management
├── submit.html        # Add repository form
├── progress.html      # Analysis pipeline status
├── login.html         # Authentication
├── error.html         # Error states
└── README.md          # This file
```
