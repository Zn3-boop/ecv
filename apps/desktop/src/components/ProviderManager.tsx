import { useState, useEffect, useCallback } from 'react';

interface Provider {
  id: string;
  name: string;
  api_url: string;
  api_key: string;
  model: string;
  enabled: boolean;
  api_type: string;
  extra: Record<string, unknown>;
}

const API_BASE = 'http://localhost:8000/provider';

export function ProviderManager() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [formData, setFormData] = useState({
    id: '',
    name: '',
    api_url: '',
    api_key: '',
    model: 'gpt-3.5-turbo',
    api_type: 'openai',
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const showMessage = useCallback((type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 3000);
  }, []);

  const fetchProviders = useCallback(async () => {
    try {
      const res = await fetch(API_BASE + '/');
      const data = await res.json();
      setProviders(data);
    } catch {
      showMessage('error', '获取Provider列表失败');
    }
  }, [showMessage]);

  useEffect(() => {
    fetchProviders();
  }, [fetchProviders]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const url = editingProvider
        ? `${API_BASE}/${editingProvider.id}`
        : API_BASE + '/';
      const method = editingProvider ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      if (res.ok) {
        showMessage('success', editingProvider ? '更新成功' : '添加成功');
        setShowForm(false);
        setEditingProvider(null);
        setFormData({ id: '', name: '', api_url: '', api_key: '', model: 'gpt-3.5-turbo', api_type: 'openai' });
        fetchProviders();
      } else {
        const err = await res.json();
        showMessage('error', err.detail || '操作失败');
      }
    } catch (err) {
      showMessage('error', '请求失败');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('确定要删除这个Provider吗？')) return;

    try {
      const res = await fetch(`${API_BASE}/${id}`, { method: 'DELETE' });
      if (res.ok) {
        showMessage('success', '删除成功');
        fetchProviders();
      }
    } catch (err) {
      showMessage('error', '删除失败');
    }
  };

  const handleTest = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/${id}/test`, { method: 'POST' });
      const data = await res.json();
      showMessage(data.success ? 'success' : 'error', data.message);
    } catch (err) {
      showMessage('error', '测试失败');
    }
  };

  const handleToggle = async (id: string, currentEnabled: boolean) => {
    try {
      const res = await fetch(`${API_BASE}/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !currentEnabled }),
      });
      if (res.ok) {
        showMessage('success', currentEnabled ? '已禁用' : '已启用');
        fetchProviders();
      }
    } catch (err) {
      showMessage('error', '切换状态失败');
    }
  };

  const addPreset = async (type: 'ollama' | 'minimax') => {
    try {
      const res = await fetch(`${API_BASE}/preset/${type}`, { method: 'POST' });
      const data = await res.json();
      showMessage('success', data.message);
      fetchProviders();
    } catch (err) {
      showMessage('error', '添加预设失败');
    }
  };

  const editProvider = (p: Provider) => {
    setEditingProvider(p);
    setFormData({
      id: p.id,
      name: p.name,
      api_url: p.api_url,
      api_key: p.api_key,
      model: p.model,
      api_type: p.api_type || 'openai',
    });
    setShowForm(true);
  };

  return (
    <div style={{ padding: '20px', maxWidth: '900px', margin: '0 auto' }}>
      <h2 style={{ marginBottom: '20px' }}>🤖 AI Provider 管理</h2>

      {message && (
        <div
          style={{
            padding: '10px 15px',
            marginBottom: '15px',
            borderRadius: '6px',
            background: message.type === 'success' ? '#d4edda' : '#f8d7da',
            color: message.type === 'success' ? '#155724' : '#721c24',
          }}
        >
          {message.text}
        </div>
      )}

      {/* 预设按钮 */}
      <div style={{ marginBottom: '20px', display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
        <button
          onClick={() => addPreset('ollama')}
          style={{
            padding: '8px 16px',
            background: '#6c757d',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
          }}
        >
          + Ollama (本地)
        </button>
        <button
          onClick={() => addPreset('minimax')}
          style={{
            padding: '8px 16px',
            background: '#17a2b8',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
          }}
        >
          + MiniMax
        </button>
        <button
          onClick={() => {
            setEditingProvider(null);
            setFormData({ id: '', name: '', api_url: '', api_key: '', model: 'gpt-3.5-turbo', api_type: 'openai' });
            setShowForm(true);
          }}
          style={{
            padding: '8px 16px',
            background: '#28a745',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
          }}
        >
          + 自定义 Provider
        </button>
      </div>

      {/* Provider 列表 */}
      <div style={{ display: 'grid', gap: '15px' }}>
        {providers.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#666' }}>
            暂无Provider，点击上方按钮添加
          </div>
        ) : (
          providers.map((p) => (
            <div
              key={p.id}
              style={{
                padding: '15px',
                border: '1px solid #ddd',
                borderRadius: '8px',
                background: '#fff',
                opacity: p.enabled ? 1 : 0.6,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '5px' }}>
                    <h3 style={{ margin: 0 }}>{p.name}</h3>
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: '10px',
                        fontSize: '12px',
                        background: p.enabled ? '#28a745' : '#6c757d',
                        color: 'white',
                      }}
                    >
                      {p.enabled ? '启用' : '禁用'}
                    </span>
                    <span
                      style={{
                        padding: '2px 8px',
                        borderRadius: '10px',
                        fontSize: '12px',
                        background: '#17a2b8',
                        color: 'white',
                      }}
                    >
                      {p.api_type}
                    </span>
                  </div>
                  <div style={{ fontSize: '13px', color: '#666' }}>
                    <div>ID: {p.id}</div>
                    <div>Model: {p.model}</div>
                    <div style={{ wordBreak: 'break-all' }}>URL: {p.api_url}</div>
                    {p.api_key && <div>Key: {'*'.repeat(8)}{p.api_key.slice(-4)}</div>}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  <button
                    onClick={() => handleTest(p.id)}
                    style={{
                      padding: '6px 12px',
                      background: '#007bff',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '13px',
                    }}
                  >
                    测试
                  </button>
                  <button
                    onClick={() => handleToggle(p.id, p.enabled)}
                    style={{
                      padding: '6px 12px',
                      background: p.enabled ? '#ffc107' : '#28a745',
                      color: p.enabled ? '#333' : 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '13px',
                    }}
                  >
                    {p.enabled ? '禁用' : '启用'}
                  </button>
                  <button
                    onClick={() => editProvider(p)}
                    style={{
                      padding: '6px 12px',
                      background: '#ffc107',
                      color: '#333',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '13px',
                    }}
                  >
                    编辑
                  </button>
                  <button
                    onClick={() => handleDelete(p.id)}
                    style={{
                      padding: '6px 12px',
                      background: '#dc3545',
                      color: 'white',
                      border: 'none',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '13px',
                    }}
                  >
                    删除
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* 添加/编辑表单 */}
      {showForm && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: 'white',
              padding: '25px',
              borderRadius: '10px',
              width: '500px',
              maxWidth: '90%',
              maxHeight: '90vh',
              overflow: 'auto',
            }}
          >
            <h3 style={{ marginTop: 0 }}>{editingProvider ? '编辑' : '添加'} Provider</h3>
            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: '15px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>ID</label>
                <input
                  type="text"
                  value={formData.id}
                  onChange={(e) => setFormData({ ...formData, id: e.target.value })}
                  disabled={!!editingProvider}
                  required
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
              <div style={{ marginBottom: '15px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>名称</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
              <div style={{ marginBottom: '15px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>API URL</label>
                <input
                  type="text"
                  value={formData.api_url}
                  onChange={(e) => setFormData({ ...formData, api_url: e.target.value })}
                  placeholder="https://api.example.com/v1 或 https://api.example.com/v1/chat/completions"
                  required
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    boxSizing: 'border-box',
                  }}
                />
                <small style={{ color: '#666', fontSize: '12px' }}>
                  支持不完整URL，系统会自动补全路径
                </small>
              </div>
              <div style={{ marginBottom: '15px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>API Key</label>
                <input
                  type="password"
                  value={formData.api_key}
                  onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                  placeholder="可选，部分API不需要Key"
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
              <div style={{ marginBottom: '15px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>默认模型</label>
                <input
                  type="text"
                  value={formData.model}
                  onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                  required
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
              <div style={{ marginBottom: '20px' }}>
                <label style={{ display: 'block', marginBottom: '5px', fontWeight: 'bold' }}>API 类型</label>
                <select
                  value={formData.api_type}
                  onChange={(e) => setFormData({ ...formData, api_type: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '8px',
                    border: '1px solid #ddd',
                    borderRadius: '4px',
                    boxSizing: 'border-box',
                  }}
                >
                  <option value="openai">OpenAI 兼容</option>
                  <option value="anthropic">Anthropic</option>
                </select>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button
                  type="button"
                  onClick={() => {
                    setShowForm(false);
                    setEditingProvider(null);
                  }}
                  style={{
                    padding: '8px 16px',
                    background: '#6c757d',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                  }}
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  style={{
                    padding: '8px 16px',
                    background: '#28a745',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: loading ? 'not-allowed' : 'pointer',
                    opacity: loading ? 0.7 : 1,
                  }}
                >
                  {loading ? '保存中...' : '保存'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
