import React, { useState, useEffect } from 'react';
import { Layout } from '../components/layout';
import { Card, CardHeader, CardTitle, CardContent, Button, Input, Badge, Modal, ModalHeader, ModalBody, ModalFooter, PageHeader } from '../components/ui';
import { useAppStore } from '../store/appStore';
import { useAuthStore } from '../store/authStore';
import {
  getUsers,
  createUser,
  updateUser,
  updateUserPassword,
  deleteUser,
  type UserResponse,
  type CreateUserRequest,
} from '../api/endpoints/users';

export const UserManagement: React.FC = () => {
  const { addToast } = useAppStore();
  const currentUser = useAuthStore((s) => s.user);
  const [users, setUsers] = useState<UserResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingPasswordId, setEditingPasswordId] = useState<number | null>(null);
  const [newPassword, setNewPassword] = useState('');

  // Create form state
  const [formData, setFormData] = useState<CreateUserRequest>({
    username: '',
    password: '',
    full_name: '',
    email: '',
    is_admin: false,
  });

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const data = await getUsers();
      setUsers(data.users);
    } catch {
      addToast('Error loading users', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createUser(formData);
      addToast('User created successfully', 'success');
      setShowCreateForm(false);
      setFormData({ username: '', password: '', full_name: '', email: '', is_admin: false });
      fetchUsers();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      addToast(typeof detail === 'string' ? detail : 'Error creating user', 'error');
    }
  };

  const handleToggleActive = async (user: UserResponse) => {
    try {
      await updateUser(user.id, { is_active: !user.is_active });
      addToast(`User ${user.is_active ? 'deactivated' : 'activated'}`, 'success');
      fetchUsers();
    } catch {
      addToast('Error updating user', 'error');
    }
  };

  const handleToggleAdmin = async (user: UserResponse) => {
    try {
      await updateUser(user.id, { is_admin: !user.is_admin });
      addToast(`Admin ${user.is_admin ? 'removed' : 'granted'}`, 'success');
      fetchUsers();
    } catch {
      addToast('Error updating user', 'error');
    }
  };

  const handlePasswordUpdate = async (userId: number) => {
    if (!newPassword || newPassword.length < 6) {
      addToast('Password must be at least 6 characters', 'warning');
      return;
    }
    try {
      await updateUserPassword(userId, newPassword);
      addToast('Password updated', 'success');
      setEditingPasswordId(null);
      setNewPassword('');
    } catch {
      addToast('Error updating password', 'error');
    }
  };

  const handleDelete = async (user: UserResponse) => {
    if (!confirm(`Are you sure you want to delete user "${user.username}"?`)) return;
    try {
      await deleteUser(user.id);
      addToast('User deleted', 'success');
      fetchUsers();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      addToast(typeof detail === 'string' ? detail : 'Error deleting user', 'error');
    }
  };

  return (
    <Layout>
      <div className="space-y-6">
        <PageHeader 
          title="User Management" 
          subtitle="Manage application users and permissions"
          actions={currentUser?.is_admin && (
            <Button onClick={() => setShowCreateForm(true)}>
              + Add User
            </Button>
          )}
        />

        {/* Create User Form */}
        {showCreateForm && (
          <Card>
            <CardHeader>
              <CardTitle>Create New User</CardTitle>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreate} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Input
                    label="Username"
                    value={formData.username}
                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                    placeholder="username"
                    required
                  />
                  <Input
                    label="Password"
                    type="password"
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    placeholder="Min 6 characters"
                    required
                  />
                  <Input
                    label="Full Name"
                    value={formData.full_name || ''}
                    onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                    placeholder="Full name"
                  />
                  <Input
                    label="Email"
                    type="email"
                    value={formData.email || ''}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    placeholder="email@example.com"
                  />
                </div>
                <div className="flex items-center space-x-4">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.is_admin}
                      onChange={(e) => setFormData({ ...formData, is_admin: e.target.checked })}
                      className="w-4 h-4 rounded"
                      style={{ accentColor: 'var(--color-primary)' }}
                    />
                    <span className="text-sm" style={{ color: 'var(--color-text)' }}>Administrator</span>
                  </label>
                </div>
                <Button type="submit">Create User</Button>
              </form>
            </CardContent>
          </Card>
        )}

        {/* Users List */}
        <Card>
          <CardHeader>
            <CardTitle>Users ({users.length})</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <p style={{ color: 'var(--color-text-muted)' }}>Loading users...</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                      <th className="text-left py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Username</th>
                      <th className="text-left py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Full Name</th>
                      <th className="text-left py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Email</th>
                      <th className="text-center py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Status</th>
                      <th className="text-center py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Role</th>
                      {currentUser?.is_admin && (
                        <th className="text-right py-3 px-4 font-medium" style={{ color: 'var(--color-text-muted)' }}>Actions</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((user) => (
                      <React.Fragment key={user.id}>
                        <tr className="transition-colors" style={{ borderBottom: '1px solid var(--color-border)' }} onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--color-surface-hover)'} onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}>
                          <td className="py-3 px-4 font-medium" style={{ color: 'var(--color-text)' }}>{user.username}</td>
                          <td className="py-3 px-4" style={{ color: 'var(--color-text)' }}>{user.full_name || '-'}</td>
                          <td className="py-3 px-4" style={{ color: 'var(--color-text)' }}>{user.email || '-'}</td>
                          <td className="py-3 px-4 text-center">
                            <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                              user.is_active
                                ? 'bg-green-900/30 text-green-400'
                                : 'bg-red-900/30 text-red-400'
                            }`}>
                              {user.is_active ? 'Active' : 'Inactive'}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-center">
                            <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                              user.is_admin
                                ? 'bg-purple-900/30 text-purple-400'
                                : 'bg-gray-800 text-gray-400'
                            }`}>
                              {user.is_admin ? 'Admin' : 'User'}
                            </span>
                          </td>
                          {currentUser?.is_admin && (
                            <td className="py-3 px-4 text-right space-x-2">
                              <Button variant="secondary" size="sm" onClick={() => handleToggleActive(user)}>
                                {user.is_active ? 'Deactivate' : 'Activate'}
                              </Button>
                              <Button variant="secondary" size="sm" onClick={() => handleToggleAdmin(user)}>
                                {user.is_admin ? 'Remove Admin' : 'Make Admin'}
                              </Button>
                              <Button variant="secondary" size="sm" onClick={() => setEditingPasswordId(editingPasswordId === user.id ? null : user.id)}>
                                Password
                              </Button>
                              {user.id !== currentUser?.id && (
                                <Button variant="danger" size="sm" onClick={() => handleDelete(user)}>
                                  Delete
                                </Button>
                              )}
                            </td>
                          )}
                        </tr>
                        {/* Password edit row */}
                        {editingPasswordId === user.id && (
                          <tr style={{ borderBottom: '1px solid var(--color-border)', backgroundColor: 'var(--color-surface-hover)' }}>
                            <td colSpan={6} className="py-3 px-4">
                              <div className="flex items-center space-x-3">
                                <span className="text-sm" style={{ color: 'var(--color-text-muted)' }}>New password for {user.username}:</span>
                                <Input
                                  type="password"
                                  value={newPassword}
                                  onChange={(e) => setNewPassword(e.target.value)}
                                  placeholder="Min 6 characters"
                                />
                                <Button variant="primary" size="sm" onClick={() => handlePasswordUpdate(user.id)}>
                                  Save
                                </Button>
                                <Button variant="secondary" size="sm" onClick={() => { setEditingPasswordId(null); setNewPassword(''); }}>
                                  Cancel
                                </Button>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
};
