'use client';

/**
 * AI Chat Assistant page — full-height chat layout for a repository.
 * Mock: specs/001-code-wiki/ux/docs-glassmorphism/chat.html
 */

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { GradientBackground } from '@/components/ui/GradientBackground';
import { api } from '@/services/api';
import type { ChatConversation, ChatMessage, ChatMessageReference, Repository } from '@/services/api';

const SUGGESTION_CHIPS = [
  'How does authentication work?',
  'What are the main modules?',
  'Where is the database schema?',
  'How are API routes structured?',
];

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user';
  return (
    <div
      style={{
        display: 'flex',
        gap: 16,
        alignItems: 'flex-start',
        animation: 'messageSlideIn 0.4s ease',
      }}
    >
      {/* Avatar */}
      <div
        style={{
          width: 40,
          height: 40,
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 18,
          flexShrink: 0,
          background: isUser
            ? 'linear-gradient(135deg, #EC4899, var(--primary))'
            : 'linear-gradient(135deg, var(--primary), var(--secondary))',
          boxShadow: isUser
            ? '0 0 20px rgba(236,72,153,0.4)'
            : '0 0 20px rgba(139,92,246,0.4)',
        }}
      >
        {isUser ? '👤' : '🤖'}
      </div>

      {/* Content */}
      <div style={{ flex: 1, maxWidth: 800 }}>
        <div
          style={{
            padding: '20px 24px',
            borderRadius: 16,
            fontSize: 15,
            lineHeight: 1.7,
            background: isUser
              ? 'linear-gradient(135deg, rgba(139,92,246,0.15), rgba(236,72,153,0.1))'
              : 'rgba(255,255,255,0.04)',
            border: `1px solid ${isUser ? 'rgba(139,92,246,0.3)' : 'var(--glass-border)'}`,
          }}
        >
          {/* Render content — split on code blocks for basic formatting */}
          {renderContent(msg.content)}
        </div>

        {/* References */}
        {msg.references && msg.references.length > 0 && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
            {msg.references.map((ref, i) => (
              <ReferenceCard key={i} ref_={ref} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ReferenceCard({ ref_ }: { ref_: ChatMessageReference }) {
  const icon = ref_.type === 'code_entity' ? '⚡' : ref_.type === 'wiki_page' ? '📄' : '📁';
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '6px 12px',
        background: 'rgba(139,92,246,0.1)',
        border: '1px solid rgba(139,92,246,0.3)',
        borderRadius: 8,
        fontSize: 12,
        color: 'var(--primary-light)',
        fontFamily: "'Fira Code', monospace",
      }}
    >
      <span>{icon}</span>
      <span>{ref_.title}</span>
    </div>
  );
}

function renderContent(text: string) {
  // Basic code block splitting
  const parts = text.split(/(```[\s\S]*?```)/g);
  return parts.map((part, i) => {
    if (part.startsWith('```')) {
      const lines = part.slice(3, -3).split('\n');
      const lang = lines[0] || '';
      const code = lines.slice(1).join('\n');
      return (
        <pre
          key={i}
          style={{
            background: 'rgba(0,0,0,0.4)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 8,
            padding: '12px 16px',
            marginTop: 8,
            marginBottom: 8,
            fontFamily: "'Fira Code', monospace",
            fontSize: 13,
            overflowX: 'auto',
            color: 'var(--secondary)',
          }}
        >
          {code}
        </pre>
      );
    }
    return <span key={i} style={{ whiteSpace: 'pre-wrap' }}>{part}</span>;
  });
}

function TypingIndicator() {
  return (
    <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
      <div
        style={{
          width: 40, height: 40, borderRadius: '50%', display: 'flex',
          alignItems: 'center', justifyContent: 'center', fontSize: 18, flexShrink: 0,
          background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
          boxShadow: '0 0 20px rgba(139,92,246,0.4)',
        }}
      >🤖</div>
      <div
        style={{
          padding: '20px 24px',
          borderRadius: 16,
          background: 'rgba(255,255,255,0.04)',
          border: '1px solid var(--glass-border)',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
        }}
      >
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            style={{
              width: 8, height: 8, borderRadius: '50%',
              background: 'var(--primary)',
              animation: `dotPulse 1.4s ${i * 0.2}s ease-in-out infinite`,
              display: 'inline-block',
            }}
          />
        ))}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const params = useParams();
  const router = useRouter();
  const owner = params.owner as string;
  const name = params.name as string;
  const base = `/${owner}/${name}`;

  const [repo, setRepo] = useState<Repository | null>(null);
  const [conversation, setConversation] = useState<ChatConversation | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Find repo + create or load conversation
  useEffect(() => {
    const init = async () => {
      try {
        const { repositories } = await api.repositories.list();
        const found = repositories.find(
          (r) =>
            r.owner?.toLowerCase() === owner.toLowerCase() &&
            r.name.toLowerCase() === name.toLowerCase()
        );
        if (!found) { setLoading(false); return; }
        setRepo(found);

        // Load existing conversations or create new
        const convs = await api.chat.listConversations(found.id).catch(() => []);
        if (convs.length > 0) {
          const conv = convs[0];
          setConversation(conv);
          setMessages(conv.messages || []);
        } else {
          const conv = await api.chat.createConversation(found.id);
          setConversation(conv);
        }
      } catch {
        // ignore
      } finally {
        setLoading(false);
      }
    };
    init();
  }, [owner, name]);

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    const ta = e.target;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  };

  const handleSend = async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || !conversation || sending) return;

    const userMsg: ChatMessage = {
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
      references: [],
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    setSending(true);

    try {
      const aiMsg = await api.chat.sendMessage(conversation.id, content);
      // api.chat.sendMessage returns ChatMessage (the AI response)
      setMessages((prev) => [...prev, aiMsg as unknown as ChatMessage]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant' as const,
          content: 'Sorry, I encountered an error. Please try again.',
          timestamp: new Date().toISOString(),
          references: [],
        },
      ]);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleNewChat = async () => {
    if (!repo) return;
    try {
      const conv = await api.chat.createConversation(repo.id);
      setConversation(conv);
      setMessages([]);
    } catch {
      // ignore
    }
  };

  return (
    <>
      <GradientBackground />
      <style>{`
        @keyframes messageSlideIn {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes dotPulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1.2); }
        }
        .chat-textarea:focus { outline: none; border-color: rgba(139,92,246,0.5) !important; }
        .chat-send-btn:hover:not(:disabled) {
          transform: translateY(-2px);
          box-shadow: 0 8px 30px rgba(139,92,246,0.5) !important;
        }
        .chat-send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .chip-btn:hover { background: rgba(139,92,246,0.2) !important; border-color: rgba(139,92,246,0.5) !important; }
      `}</style>

      <div
        style={{
          maxWidth: 1000,
          margin: '0 auto',
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          padding: '24px',
          gap: 16,
        }}
      >
        {/* Header */}
        <div
          style={{
            background: 'var(--glass-bg)',
            backdropFilter: 'blur(20px)',
            border: '1px solid var(--glass-border)',
            borderRadius: 20,
            padding: '20px 28px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 16,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
            <Link
              href={base}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                textDecoration: 'none',
              }}
            >
              <div
                style={{
                  width: 40, height: 40,
                  background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
                  borderRadius: 10,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontWeight: 800, fontSize: 16,
                  boxShadow: '0 0 24px rgba(139,92,246,0.5)',
                }}
              >⚡</div>
              <span
                style={{
                  fontSize: 18, fontWeight: 700,
                  background: 'linear-gradient(135deg, var(--primary-light), var(--secondary))',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                }}
              >Code Wiki</span>
            </Link>
            <div style={{ width: 1, height: 24, background: 'var(--glass-border)' }} />
            <div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>AI Chat Assistant</div>
              <div style={{ fontSize: 12, color: 'var(--text-tertiary)', marginTop: 2 }}>
                {repo ? `${repo.owner}/${repo.name}` : `${owner}/${name}`}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <Link
              href={base}
              style={{
                padding: '8px 16px',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--glass-border)',
                borderRadius: 10,
                color: 'var(--text-primary)',
                fontSize: 13,
                fontWeight: 600,
                textDecoration: 'none',
                transition: 'all 0.2s',
              }}
            >
              ← Wiki
            </Link>
            <button
              onClick={handleNewChat}
              style={{
                padding: '8px 16px',
                background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
                border: 'none',
                borderRadius: 10,
                color: 'white',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.2s',
                boxShadow: '0 4px 20px rgba(139,92,246,0.3)',
              }}
            >
              + New Chat
            </button>
          </div>
        </div>

        {/* Messages */}
        <div
          style={{
            flex: 1,
            background: 'var(--glass-bg)',
            backdropFilter: 'blur(20px)',
            border: '1px solid var(--glass-border)',
            borderRadius: 20,
            padding: '28px 32px',
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 24,
          }}
        >
          {loading && (
            <div style={{ color: 'var(--text-tertiary)', textAlign: 'center', marginTop: 40 }}>
              Loading…
            </div>
          )}

          {!loading && messages.length === 0 && (
            <div style={{ textAlign: 'center', marginTop: 60 }}>
              <div style={{ fontSize: 48, marginBottom: 16 }}>🤖</div>
              <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>
                Ask me anything about {name}
              </h2>
              <p style={{ color: 'var(--text-secondary)', marginBottom: 32 }}>
                I have full knowledge of the codebase, modules, and architecture.
              </p>
              {/* Suggestion chips */}
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', justifyContent: 'center' }}>
                {SUGGESTION_CHIPS.map((chip) => (
                  <button
                    key={chip}
                    className="chip-btn"
                    onClick={() => handleSend(chip)}
                    style={{
                      padding: '10px 16px',
                      background: 'rgba(255,255,255,0.04)',
                      border: '1px solid var(--glass-border)',
                      borderRadius: 12,
                      color: 'var(--secondary)',
                      fontSize: 13,
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                    }}
                  >
                    {chip}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <MessageBubble key={i} msg={msg} />
          ))}

          {sending && <TypingIndicator />}

          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div
          style={{
            background: 'var(--glass-bg)',
            backdropFilter: 'blur(20px)',
            border: '1px solid var(--glass-border)',
            borderRadius: 20,
            padding: '16px 20px',
            display: 'flex',
            gap: 12,
            alignItems: 'flex-end',
          }}
        >
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            rows={1}
            placeholder="Ask about the codebase… (Shift+Enter for newline)"
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            style={{
              flex: 1,
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid var(--glass-border)',
              borderRadius: 12,
              padding: '12px 16px',
              color: 'var(--text-primary)',
              fontSize: 14,
              lineHeight: 1.6,
              resize: 'none',
              fontFamily: 'inherit',
              transition: 'border-color 0.2s',
              maxHeight: 160,
              overflowY: 'auto',
            }}
          />
          <button
            className="chat-send-btn"
            onClick={() => handleSend()}
            disabled={!input.trim() || sending}
            style={{
              width: 48, height: 48,
              background: 'linear-gradient(135deg, var(--primary), var(--secondary))',
              border: 'none', borderRadius: 12,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 20, cursor: 'pointer', flexShrink: 0,
              boxShadow: '0 4px 20px rgba(139,92,246,0.3)',
              transition: 'all 0.2s',
            }}
          >
            ➤
          </button>
        </div>
      </div>
    </>
  );
}
