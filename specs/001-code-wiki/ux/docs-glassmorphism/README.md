# Code Wiki - Glassmorphism Design System Mockups

Production-grade HTML mockups for all Code Wiki use cases with comprehensive mobile responsiveness.

## Pages Overview

### 1. **index.html** - Navigation Hub
Entry point with links to all mockup pages.

### 2. **home.html** - Repository Home Page
**Purpose:** Landing page for a repository's documentation

**Features:**
- Repository overview with title, description, and metadata
- Statistics grid (modules, functions, classes, LOC)
- Quick links section (Getting Started, API Reference, AI Assistant)
- Module cards grid (8 modules with icons, stats, descriptions)
- Recent activity timeline
- Fully responsive with mobile-optimized navigation

**Mobile Breakpoints:**
- 768px: Two-column stats grid, single-column links
- 480px: Single-column everything, stacked layout

---

### 3. **module.html** - Module Documentation Page
**Purpose:** Detailed documentation for a specific module (e.g., Repository Analysis)

**Features:**
- Three-column layout (left nav, main content, right TOC)
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

### 4. **function.html** - Function Detail Page
**Purpose:** In-depth documentation for individual functions/classes

**Features:**
- Function signature with syntax highlighting
- Parameters table (name, type, description, required)
- Return value documentation
- Multiple usage examples with copy buttons
- "Called By" and "Calls" relationship sections with cards
- Source code preview with GitHub link
- Type annotations and code highlighting
- Mobile-optimized tables and code blocks

**Mobile Breakpoints:**
- 900px: Single-column layout, mobile menu toggle
- 480px: Smaller fonts, stacked metadata

---

### 5. **search.html** - Search Results Page
**Purpose:** Search interface with filtering and results

**Features:**
- Prominent search bar with icon
- Tab filters (All, Functions, Classes, Modules, Documentation)
- Left sidebar with type/module/visibility filters
- Result cards with:
  - Type badges (Function, Class, Module)
  - Highlighted search terms
  - File location and metadata
  - Code previews
- Sort options (Relevance, Name, Module, Recently Updated)
- Empty state placeholder

**Mobile Breakpoints:**
- 900px: Sidebar becomes overlay, mobile filter toggle
- 480px: Stacked result metadata, full-width sort

---

### 6. **chat.html** - AI Chat Interface
**Purpose:** Conversational AI assistant for codebase questions

**Features:**
- Full-height chat layout
- Empty state with example questions
- Sample conversation showing:
  - User and AI message bubbles
  - Code blocks with syntax highlighting and copy buttons
  - Link cards to related documentation
  - Suggested follow-up questions
- Auto-resizing textarea input
- Send button with keyboard shortcuts (Enter to send, Shift+Enter for new line)
- Message timestamps
- Safe DOM manipulation (XSS prevention)

**Mobile Breakpoints:**
- 768px: Stacked header, full-width input
- 480px: Smaller avatars, compact message bubbles

---

### 7. **getting-started.html** - Setup Guide
**Purpose:** Step-by-step installation and configuration guide

**Features:**
- Prerequisites checklist with icons
- Numbered step cards (5 installation steps)
- Code blocks with copy buttons
- Configuration examples (.env, YAML)
- Info boxes for tips and success messages
- Quick links grid for next steps
- Comprehensive responsive design

**Mobile Breakpoints:**
- 1400px: Two-column layout (hides right TOC)
- 900px: Single column, mobile menu
- 480px: Full-width quick links

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

### Components

#### Glass Cards
```css
background: var(--glass-bg);
backdrop-filter: blur(20px);
border: 1px solid var(--glass-border);
border-radius: 20px;
box-shadow: 0 8px 32px rgba(0, 0, 0, 0.37);
```

#### Gradient Orbs
- Three animated gradient spheres
- Float animation (20s infinite)
- Blur filter (120px)
- Different colors (primary/secondary, accent/primary, secondary/primary-light)

#### Buttons
- Primary: Gradient (primary → secondary)
- Hover: Lift effect (-2px translateY)
- Shadow: Glow with matching colors

### Animations
- **fadeInUp:** Staggered entrance (0.6s, 0.8s delays)
- **messageSlideIn:** Chat messages (0.4s)
- **float:** Background orbs (20s infinite)

### Accessibility
- Keyboard navigation support
- Focus states on all interactive elements
- ARIA-compatible structure
- Touch-friendly targets (44px minimum on mobile)
- High contrast text

### Mobile Responsiveness

**All pages implement:**
1. **Mobile-First CSS:** Base styles for 320px+
2. **Breakpoints:**
   - `1400px` - Hide right sidebar
   - `900px` - Single column, mobile menu
   - `768px` - Tablet optimizations
   - `480px` - Phone optimizations
3. **Touch Optimizations:**
   - Larger tap targets
   - Hamburger menus
   - Collapsible sections
   - Auto-resizing inputs
4. **Performance:**
   - Minimal JavaScript
   - CSS animations (GPU-accelerated)
   - No external dependencies (except fonts)

## File Structure
```
docs-glassmorphism/
├── index.html              # Navigation hub
├── home.html               # Repository home page
├── module.html             # Module documentation
├── function.html           # Function detail page
├── search.html             # Search results
├── chat.html               # AI chat interface
├── getting-started.html    # Setup guide
└── README.md              # This file
```

## Testing Checklist

### Desktop (1440px+)
- [ ] All three-column layouts render correctly
- [ ] Gradient backgrounds animate smoothly
- [ ] Hover states work on all interactive elements
- [ ] Code syntax highlighting displays properly
- [ ] TOC scroll spy activates correctly

### Tablet (768px-1023px)
- [ ] Two-column layouts adapt properly
- [ ] Search filters accessible
- [ ] Module cards adjust to grid
- [ ] Navigation remains usable

### Mobile (320px-767px)
- [ ] Hamburger menus work
- [ ] Single-column layouts stack properly
- [ ] Touch targets are 44px minimum
- [ ] Chat input auto-resizes
- [ ] Code blocks scroll horizontally
- [ ] Search results stack vertically

### Cross-Browser
- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari (iOS and macOS)
- [ ] Mobile browsers (iOS Safari, Chrome Android)

### Functionality
- [ ] All internal links navigate correctly
- [ ] Copy buttons work on code blocks
- [ ] Search input accepts input
- [ ] Chat textarea resizes automatically
- [ ] Smooth scrolling works
- [ ] Mobile menus close on outside click

## Technical Details

### No External Dependencies
All pages are self-contained with:
- Inline CSS (no external stylesheets)
- Inline JavaScript (minimal, vanilla JS)
- Only external dependency: Google Fonts (Outfit, Fira Code)

### Browser Support
- Modern browsers (Chrome 90+, Firefox 88+, Safari 14+, Edge 90+)
- CSS features: backdrop-filter, grid, flexbox, CSS variables
- JavaScript: ES6+ (const, let, arrow functions, template literals)

### Performance
- Lazy loading of fonts
- GPU-accelerated animations
- Optimized repaints
- Minimal JavaScript execution

## Future Enhancements

Potential improvements for production:
1. **Accessibility:** Enhanced screen reader support, keyboard shortcuts
2. **Dark/Light Mode:** Theme toggle
3. **Internationalization:** Multi-language support
4. **Search:** Live search with debouncing
5. **Chat:** WebSocket for real-time AI responses
6. **Code:** Syntax highlighting library (e.g., Prism.js)
7. **Analytics:** Usage tracking
8. **Progressive Web App:** Offline support, installability

## License
These mockups are part of the Code Wiki project and follow the same license.
