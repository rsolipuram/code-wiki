# Comprehensive Architectural Specification: openai-cs-agents-demo

**Analysis Date:** March 5, 2026  
**Agent Model:** DeepSeek-V3  
**Architecture Style:** Multi-Agent Orchestration (Monolith)

---

## 🏛️ System Layers

### 1. Presentation Layer (Frontend)
Handles the React-based user interface, state management for the chat interface, and the integration with the OpenAI ChatKit SDK.
*   **Key Abstractions:** UI State Synchronization, Real-time Event Streaming.

### 2. Orchestration Layer (Backend Core)
The central "brain" of the application. It implements the FastAPI server and the ChatKit protocol handler.
*   **Key Abstractions:** Agent Execution Pipeline, Conversation State Management.

### 3. Domain Layer (Airline Intelligence)
Contains the specific logic for the airline demo, including specialized agents (Booking, Triage, etc.) and their executable tools.
*   **Key Abstractions:** Guardrail Enforcement, Mock Data Generation.

---

## 📦 Detailed Component Catalog

### 1. Frontend Application
*   **Purpose:** Main entry point and layout for the web interface.
*   **Public Interfaces:** `Home` (Main Page), `RootLayout`.
*   **Files:** `ui/app/layout.tsx`, `ui/app/page.tsx`, `ui/next.config.mjs`, `ui/postcss.config.mjs`, `ui/tailwind.config.ts`.

### 2. UI Components (Core)
*   **Purpose:** Specialized React components for the agent demo interface.
*   **Public Interfaces:** `AgentPanel`, `AgentsList`, `ChatKitPanel`, `ConversationContext`, `GuardrailsPanel`, `RunnerOutput`, `SeatMap`.
*   **Dependencies:** API Client.
*   **Files:** `ui/components/agent-panel.tsx`, `ui/components/agents-list.tsx`, `ui/components/chatkit-panel.tsx`, `ui/components/conversation-context.tsx`, `ui/components/guardrails.tsx`, `ui/components/panel-section.tsx`, `ui/components/runner-output.tsx`, `ui/components/seat-map.tsx`.

### 3. API Client (Frontend)
*   **Purpose:** The bridge between React and the FastAPI backend.
*   **Public Interfaces:** `fetchThreadState`, `fetchBootstrapState`, `cn` (Utility).
*   **Files:** `ui/lib/api.ts`, `ui/lib/types.ts`, `ui/lib/utils.ts`.

### 4. Web Server (FastAPI)
*   **Purpose:** Handles HTTP routing and WebSocket/SSE streaming.
*   **Public Interfaces:** `/chatkit` (Endpoint), `chatkit_state_stream`.
*   **Dependencies:** ChatKit Server.
*   **Files:** `python-backend/main.py`.

### 5. ChatKit Server
*   **Purpose:** Orchestrates the multi-agent conversation flow.
*   **Public Interfaces:** `AirlineServer.respond`, `AirlineServer.snapshot`, `AirlineServer.process`.
*   **Dependencies:** Memory Store, Agent Orchestration.
*   **Files:** `python-backend/server.py`.

### 6. Memory Store
*   **Purpose:** In-memory persistence for threads and messages.
*   **Public Interfaces:** `MemoryStore.load_threads`, `MemoryStore.save_item`, `MemoryStore.load_thread_items`.
*   **Files:** `python-backend/memory_store.py`.

### 7. Agent Orchestration
*   **Purpose:** Defines and manages the various airline agent personas.
*   **Public Interfaces:** `flight_status_agent`, `booking_agent`, `triage_agent`.
*   **Dependencies:** Tools, Guardrails.
*   **Files:** `python-backend/airline/agents.py`.

### 8. Domain Tools
*   **Purpose:** Actionable functions that agents can execute.
*   **Public Interfaces:** `flight_status_tool`, `get_matching_flights`, `book_new_flight`, `issue_compensation`.
*   **Dependencies:** Demo Data.
*   **Files:** `python-backend/airline/tools.py`.

### 9. Guardrails
*   **Purpose:** Security and policy enforcement for AI responses.
*   **Public Interfaces:** `relevance_guardrail`, `jailbreak_guardrail`.
*   **Files:** `python-backend/airline/guardrails.py`.

### 10. Context & Data Management
*   **Purpose:** Mock data generation and runtime context management.
*   **Public Interfaces:** `apply_itinerary_defaults`, `get_itinerary_for_flight`, `AirlineAgentChatContext`.
*   **Files:** `python-backend/airline/context.py`, `python-backend/airline/demo_data.py`.

---

## 🔄 Sequence: Message Response Flow

1.  **User Message:** UI sends message via `ChatKitPanel` → `API Client`.
2.  **API Gateway:** `FastAPI` receives request → `AirlineServer.respond`.
3.  **Triage:** `Triage Agent` evaluates request context using `Guardrails`.
4.  **Tool Execution:** If needed, `Flight Status Agent` calls `flight_status_tool`.
5.  **Data Retrieval:** `Tool` fetches mock data from `Demo Data`.
6.  **Persistence:** Result saved to `Memory Store`.
7.  **Broadcast:** `AirlineServer` streams the agent response + updated `SeatMap` state back to UI.

---

## 🧪 Key Technical Abstractions
*   **Agent Persona Definition:** Decoupling agent instructions from tool implementation.
*   **Fuzzy Tool Calling:** Using LLM reasoning to map user intent to Python functions.
*   **Hierarchical Triage:** A specific pattern where a "Master" agent delegates to "Expert" agents.
*   **Stateless Frontend / Stateful Backend:** The server maintains conversation state in RAM, allowing the UI to remain highly reactive.

---

## 📁 Source File Inventory (All 27 Mapped)
*   **Total React/TSX:** 14 files (Presentation)
*   **Total Python:** 10 files (Orchestration/Domain)
*   **Total Config/Metadata:** 3 files
