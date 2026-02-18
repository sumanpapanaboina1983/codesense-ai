import { useState, useRef, useEffect } from 'react';
import {
  Send,
  Bot,
  User,
  Loader2,
  Code2,
  Sparkles,
  FileCode,
  ExternalLink,
  AlertCircle,
  Database,
} from 'lucide-react';
import { getRepositories, sendChatMessage } from '../../api/client';
import type { Repository, ChatMessage, Citation } from '../../types';
import './Chat.css';

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>('');
  const [loadingRepos, setLoadingRepos] = useState(true);
  const [_error, setError] = useState<string | null>(null);
  const [expandedCitations, setExpandedCitations] = useState<Set<string>>(
    new Set()
  );
  const [conversationId, setConversationId] = useState<string | undefined>();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load repositories on mount
  useEffect(() => {
    const loadRepositories = async () => {
      try {
        setLoadingRepos(true);
        const repos = await getRepositories({ analysis_status: 'completed' });
        setRepositories(repos);
        if (repos.length === 1) {
          setSelectedRepo(repos[0].id);
        }
      } catch (err) {
        console.error('Failed to load repositories:', err);
        setError('Failed to load repositories');
      } finally {
        setLoadingRepos(false);
      }
    };
    loadRepositories();
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading || !selectedRepo) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setError(null);

    try {
      const response = await sendChatMessage(
        selectedRepo,
        userMessage.content,
        conversationId
      );

      // Update conversation ID for continuity
      setConversationId(response.conversation_id);

      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.answer,
        citations: response.citations,
        related_entities: response.related_entities,
        follow_up_suggestions: response.follow_up_suggestions,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: unknown) {
      const errorMessage =
        err instanceof Error ? err.message : 'Failed to get response';
      setError(errorMessage);

      // Add error message to chat
      const errorChatMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Sorry, I encountered an error: ${errorMessage}. Please try again.`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorChatMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleFollowUpClick = (question: string) => {
    setInput(question);
    textareaRef.current?.focus();
  };

  const toggleCitation = (citationId: string, messageId: string) => {
    const key = `${messageId}-${citationId}`;
    setExpandedCitations((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const renderAnswerWithCitations = (content: string, messageId: string) => {
    // Replace [1], [2], etc. with clickable badges
    const parts = content.split(/(\[\d+\])/g);
    return parts.map((part, index) => {
      const match = part.match(/\[(\d+)\]/);
      if (match) {
        const citationId = match[1];
        return (
          <button
            key={index}
            className="citation-badge"
            onClick={() => toggleCitation(citationId, messageId)}
            title={`View citation ${citationId}`}
          >
            {part}
          </button>
        );
      }
      return <span key={index}>{part}</span>;
    });
  };

  const renderCitationSnippet = (
    citation: Citation,
    messageId: string,
    isExpanded: boolean
  ) => {
    const key = `${messageId}-${citation.id}`;
    if (!isExpanded) return null;

    return (
      <div key={key} className="citation-expanded">
        <div className="citation-header">
          <FileCode size={14} />
          <span className="citation-file">{citation.file_path}</span>
          <span className="citation-lines">
            Lines {citation.line_start}-{citation.line_end}
          </span>
        </div>
        {citation.entity_name && (
          <div className="citation-entity">{citation.entity_name}</div>
        )}
        <pre className="citation-code">
          <code>{citation.snippet}</code>
        </pre>
      </div>
    );
  };

  const suggestedQuestions = [
    'What classes exist in this codebase?',
    'How is authentication implemented?',
    'What are the main dependencies between components?',
    'Show me the API endpoints',
  ];

  const selectedRepoData = repositories.find((r) => r.id === selectedRepo);

  return (
    <div className="chat-page">
      {/* Repository Selector */}
      <div className="chat-header">
        <div className="repo-selector">
          <Database size={18} />
          {loadingRepos ? (
            <span className="loading-text">
              <Loader2 className="spin" size={14} /> Loading repositories...
            </span>
          ) : repositories.length === 0 ? (
            <span className="no-repos">
              <AlertCircle size={14} /> No analyzed repositories available
            </span>
          ) : (
            <select
              value={selectedRepo}
              onChange={(e) => {
                setSelectedRepo(e.target.value);
                setMessages([]);
                setConversationId(undefined);
              }}
              className="repo-select"
            >
              <option value="">Select a repository...</option>
              {repositories.map((repo) => (
                <option key={repo.id} value={repo.id}>
                  {repo.name}
                </option>
              ))}
            </select>
          )}
        </div>
        {selectedRepoData && (
          <div className="selected-repo-info">
            <span className="repo-name">{selectedRepoData.name}</span>
            {selectedRepoData.url && (
              <a
                href={selectedRepoData.url}
                target="_blank"
                rel="noopener noreferrer"
                className="repo-link"
              >
                <ExternalLink size={14} />
              </a>
            )}
          </div>
        )}
      </div>

      <div className="chat-container">
        {!selectedRepo ? (
          <div className="chat-welcome">
            <div className="welcome-icon">
              <Database size={48} />
            </div>
            <h1>Select a Repository</h1>
            <p>
              Choose an analyzed repository from the dropdown above to start
              asking questions about the codebase.
            </p>
            {repositories.length === 0 && !loadingRepos && (
              <div className="no-repos-message">
                <AlertCircle size={20} />
                <p>
                  No analyzed repositories found. Please analyze a repository
                  first from the Repositories page.
                </p>
              </div>
            )}
          </div>
        ) : messages.length === 0 ? (
          <div className="chat-welcome">
            <div className="welcome-icon">
              <Code2 size={48} />
            </div>
            <h1>Code Assistant</h1>
            <p>
              Ask questions about <strong>{selectedRepoData?.name}</strong> and
              get intelligent insights powered by AI.
            </p>

            <div className="suggested-questions">
              <h3>
                <Sparkles size={16} /> Suggested Questions
              </h3>
              <div className="question-grid">
                {suggestedQuestions.map((question, index) => (
                  <button
                    key={index}
                    className="question-card"
                    onClick={() => setInput(question)}
                  >
                    {question}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="chat-messages">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`message ${message.role === 'user' ? 'user-message' : 'assistant-message'}`}
              >
                <div className="message-avatar">
                  {message.role === 'user' ? (
                    <User size={20} />
                  ) : (
                    <Bot size={20} />
                  )}
                </div>
                <div className="message-content">
                  <div className="message-header">
                    <span className="message-role">
                      {message.role === 'user' ? 'You' : 'Code Assistant'}
                    </span>
                    <span className="message-time">
                      {message.timestamp.toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </span>
                  </div>
                  <div className="message-text">
                    {message.role === 'assistant' && message.citations
                      ? renderAnswerWithCitations(message.content, message.id)
                      : message.content}
                  </div>

                  {/* Expanded Citations */}
                  {message.citations && message.citations.length > 0 && (
                    <div className="citations-container">
                      {message.citations.map((citation) =>
                        renderCitationSnippet(
                          citation,
                          message.id,
                          expandedCitations.has(`${message.id}-${citation.id}`)
                        )
                      )}
                    </div>
                  )}

                  {/* Related Entities */}
                  {message.related_entities &&
                    message.related_entities.length > 0 && (
                      <div className="related-entities">
                        <span className="related-label">Related:</span>
                        {message.related_entities.slice(0, 5).map((entity) => (
                          <span
                            key={entity.name}
                            className="entity-chip"
                            title={`${entity.type} in ${entity.file_path}`}
                          >
                            {entity.name}
                          </span>
                        ))}
                      </div>
                    )}

                  {/* Follow-up Suggestions */}
                  {message.follow_up_suggestions &&
                    message.follow_up_suggestions.length > 0 && (
                      <div className="follow-up-suggestions">
                        <span className="follow-up-label">
                          <Sparkles size={12} /> Follow-up questions:
                        </span>
                        <div className="follow-up-buttons">
                          {message.follow_up_suggestions
                            .slice(0, 3)
                            .map((suggestion, idx) => (
                              <button
                                key={idx}
                                className="follow-up-btn"
                                onClick={() => handleFollowUpClick(suggestion)}
                              >
                                {suggestion}
                              </button>
                            ))}
                        </div>
                      </div>
                    )}
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="message assistant-message">
                <div className="message-avatar">
                  <Bot size={20} />
                </div>
                <div className="message-content">
                  <div className="typing-indicator">
                    <Loader2 className="spin" size={16} />
                    <span>Analyzing codebase...</span>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}

        <form className="chat-input-form" onSubmit={handleSubmit}>
          <div className="input-wrapper">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                selectedRepo
                  ? 'Ask a question about the codebase...'
                  : 'Select a repository first...'
              }
              rows={1}
              disabled={isLoading || !selectedRepo}
            />
            <button
              type="submit"
              className="send-button"
              disabled={!input.trim() || isLoading || !selectedRepo}
            >
              {isLoading ? (
                <Loader2 className="spin" size={20} />
              ) : (
                <Send size={20} />
              )}
            </button>
          </div>
          <p className="input-hint">
            Press Enter to send, Shift+Enter for new line
          </p>
        </form>
      </div>
    </div>
  );
}
