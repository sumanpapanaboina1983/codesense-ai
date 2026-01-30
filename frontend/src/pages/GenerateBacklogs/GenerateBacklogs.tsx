import { useState, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import {
  ListTodo,
  Upload,
  Layers,
  Send,
  Loader2,
  CheckCircle,
  RefreshCw,
  Bot,
  User,
  Download,
  ExternalLink,
  Plus,
  Trash2,
  GripVertical,
} from 'lucide-react';
import './GenerateBacklogs.css';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

interface BacklogItem {
  id: string;
  title: string;
  description: string;
  priority: 'High' | 'Medium' | 'Low';
  points: number;
  status: 'draft' | 'approved' | 'created';
}

export function GenerateBacklogs() {
  const location = useLocation();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [step, setStep] = useState<'upload' | 'chat' | 'review'>('upload');
  const [epicContent, setEpicContent] = useState<string>(location.state?.epicContent || '');
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [backlogs, setBacklogs] = useState<BacklogItem[]>([]);

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        setEpicContent(content);
        startChatWithEPIC();
      };
      reader.readAsText(file);
    }
  };

  const startChatWithEPIC = () => {
    setStep('chat');
    setMessages([
      {
        id: '1',
        role: 'assistant',
        content: `I've analyzed your EPIC document. Based on the user stories and requirements, I can help you create detailed backlog items.\n\nI've identified the following potential backlog items:\n- User Registration API endpoint\n- Login form component\n- JWT token management\n- Role assignment UI\n- Password reset flow\n\nWould you like me to generate detailed backlog items with story points and acceptance criteria, or do you want to prioritize specific items first?`,
      },
    ]);
  };

  const handleUseEPIC = () => {
    if (epicContent) {
      startChatWithEPIC();
    }
  };

  const handleSendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content: input.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    setTimeout(() => {
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'I\'ve noted your priorities. I\'ll structure the backlog items accordingly with appropriate story points and detailed acceptance criteria.\n\nClick "Generate Backlogs" when you\'re ready to see the complete backlog list.',
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setIsLoading(false);
    }, 1500);
  };

  const handleGenerateBacklogs = () => {
    setIsLoading(true);
    setTimeout(() => {
      setBacklogs([
        {
          id: '1',
          title: 'Implement User Registration API',
          description: 'Create REST API endpoint for user registration with email validation and password hashing.',
          priority: 'High',
          points: 5,
          status: 'draft',
        },
        {
          id: '2',
          title: 'Create Login Form Component',
          description: 'Build responsive login form with email/password fields, validation, and error handling.',
          priority: 'High',
          points: 3,
          status: 'draft',
        },
        {
          id: '3',
          title: 'Implement JWT Token Management',
          description: 'Set up JWT token generation, validation, and refresh token rotation.',
          priority: 'High',
          points: 5,
          status: 'draft',
        },
        {
          id: '4',
          title: 'Build Password Reset Flow',
          description: 'Create forgot password functionality with email verification and secure reset link.',
          priority: 'Medium',
          points: 5,
          status: 'draft',
        },
        {
          id: '5',
          title: 'Create Role Assignment UI',
          description: 'Admin interface for viewing and assigning user roles with permission management.',
          priority: 'Medium',
          points: 8,
          status: 'draft',
        },
        {
          id: '6',
          title: 'Implement Rate Limiting',
          description: 'Add rate limiting to authentication endpoints to prevent brute force attacks.',
          priority: 'Medium',
          points: 3,
          status: 'draft',
        },
        {
          id: '7',
          title: 'Add Audit Logging',
          description: 'Log authentication events and role changes for compliance and security monitoring.',
          priority: 'Low',
          points: 3,
          status: 'draft',
        },
      ]);
      setStep('review');
      setIsLoading(false);
    }, 2000);
  };

  const handleCreateInJira = async (id: string) => {
    setBacklogs((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, status: 'created' } : item
      )
    );
  };

  const handleCreateAllInJira = async () => {
    setIsLoading(true);
    setTimeout(() => {
      setBacklogs((prev) =>
        prev.map((item) => ({ ...item, status: 'created' }))
      );
      setIsLoading(false);
    }, 2000);
  };

  const handleDeleteItem = (id: string) => {
    setBacklogs((prev) => prev.filter((item) => item.id !== id));
  };

  const handleDownload = () => {
    const content = backlogs
      .map(
        (item) =>
          `## ${item.title}\n- **Priority:** ${item.priority}\n- **Story Points:** ${item.points}\n- **Description:** ${item.description}\n`
      )
      .join('\n');
    const blob = new Blob([`# Backlog Items\n\n${content}`], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Backlogs-${new Date().toISOString().split('T')[0]}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const getPriorityColor = (priority: string) => {
    switch (priority) {
      case 'High':
        return 'badge-error';
      case 'Medium':
        return 'badge-warning';
      case 'Low':
        return 'badge-info';
      default:
        return 'badge-pending';
    }
  };

  return (
    <div className="generate-backlogs-page">
      {/* Progress Steps */}
      <div className="workflow-stepper">
        <div className={`step ${step === 'upload' ? 'active' : ''} ${step !== 'upload' ? 'completed' : ''}`}>
          <div className="step-number">{step !== 'upload' ? <CheckCircle size={16} /> : '1'}</div>
          <span className="step-label">Upload EPIC</span>
        </div>
        <div className={`step ${step === 'chat' ? 'active' : ''} ${step === 'review' ? 'completed' : ''}`}>
          <div className="step-number">{step === 'review' ? <CheckCircle size={16} /> : '2'}</div>
          <span className="step-label">Refine Items</span>
        </div>
        <div className={`step ${step === 'review' ? 'active' : ''}`}>
          <div className="step-number">3</div>
          <span className="step-label">Review & Create</span>
        </div>
      </div>

      {/* Step 1: Upload EPIC */}
      {step === 'upload' && (
        <div className="step-content">
          <div className="step-header">
            <ListTodo size={32} className="step-icon" />
            <h2>Generate Backlogs from EPIC</h2>
            <p>Upload your EPIC document or use one from a previous generation</p>
          </div>

          <div className="upload-options">
            {epicContent && (
              <div className="existing-epic">
                <div className="epic-preview-card">
                  <Layers size={24} />
                  <div>
                    <h3>EPIC from Previous Step</h3>
                    <p>Use the EPIC you just generated</p>
                  </div>
                  <button className="btn btn-primary" onClick={handleUseEPIC}>
                    Use This EPIC
                  </button>
                </div>
              </div>
            )}

            <div className="upload-zone" onClick={() => fileInputRef.current?.click()}>
              <Upload size={48} />
              <h3>Upload EPIC Document</h3>
              <p>Drag and drop or click to browse</p>
              <span className="file-types">Supports: .md, .txt, .docx</span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".md,.txt,.docx"
                onChange={handleFileUpload}
                style={{ display: 'none' }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Step 2: Chat Interface */}
      {step === 'chat' && (
        <div className="chat-step">
          <div className="chat-header">
            <h2>Refine Backlog Items</h2>
            <button className="btn btn-primary" onClick={handleGenerateBacklogs} disabled={isLoading}>
              {isLoading ? <Loader2 className="spin" size={16} /> : <ListTodo size={16} />}
              Generate Backlogs
            </button>
          </div>

          <div className="chat-messages">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`message ${message.role === 'user' ? 'user-message' : 'assistant-message'}`}
              >
                <div className="message-avatar">
                  {message.role === 'user' ? <User size={18} /> : <Bot size={18} />}
                </div>
                <div className="message-content">{message.content}</div>
              </div>
            ))}
            {isLoading && (
              <div className="message assistant-message">
                <div className="message-avatar">
                  <Bot size={18} />
                </div>
                <div className="message-content typing">
                  <Loader2 className="spin" size={16} />
                  <span>Thinking...</span>
                </div>
              </div>
            )}
          </div>

          <div className="chat-input">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
              placeholder="Add more context or prioritize items..."
              disabled={isLoading}
            />
            <button
              className="send-btn"
              onClick={handleSendMessage}
              disabled={!input.trim() || isLoading}
            >
              <Send size={20} />
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Review */}
      {step === 'review' && (
        <div className="review-step">
          <div className="review-header">
            <div className="header-left">
              <h2>Review Backlog Items</h2>
              <span className="item-count">{backlogs.length} items</span>
            </div>
            <div className="review-actions">
              <button className="btn btn-outline" onClick={() => setStep('chat')}>
                <RefreshCw size={16} />
                Refine
              </button>
              <button className="btn btn-secondary" onClick={handleDownload}>
                <Download size={16} />
                Download
              </button>
              <button
                className="btn btn-primary"
                onClick={handleCreateAllInJira}
                disabled={isLoading || backlogs.every((b) => b.status === 'created')}
              >
                {isLoading ? <Loader2 className="spin" size={16} /> : <ExternalLink size={16} />}
                Create All in JIRA
              </button>
            </div>
          </div>

          <div className="backlog-list">
            {backlogs.map((item) => (
              <div key={item.id} className={`backlog-item ${item.status === 'created' ? 'created' : ''}`}>
                <div className="drag-handle">
                  <GripVertical size={16} />
                </div>
                <div className="item-content">
                  <div className="item-header">
                    <h3>{item.title}</h3>
                    <div className="item-meta">
                      <span className={`badge ${getPriorityColor(item.priority)}`}>
                        {item.priority}
                      </span>
                      <span className="story-points">{item.points} pts</span>
                    </div>
                  </div>
                  <p className="item-description">{item.description}</p>
                </div>
                <div className="item-actions">
                  {item.status === 'created' ? (
                    <span className="created-badge">
                      <CheckCircle size={16} />
                      Created
                    </span>
                  ) : (
                    <>
                      <button
                        className="btn btn-sm btn-outline"
                        onClick={() => handleCreateInJira(item.id)}
                      >
                        <Plus size={14} />
                        JIRA
                      </button>
                      <button
                        className="btn-icon-danger"
                        onClick={() => handleDeleteItem(item.id)}
                      >
                        <Trash2 size={16} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="backlog-summary">
            <div className="summary-item">
              <span className="summary-label">Total Items</span>
              <span className="summary-value">{backlogs.length}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Total Points</span>
              <span className="summary-value">{backlogs.reduce((sum, b) => sum + b.points, 0)}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Created in JIRA</span>
              <span className="summary-value">{backlogs.filter((b) => b.status === 'created').length}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
