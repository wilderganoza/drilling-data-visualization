import { apiClient } from '../client';

export interface UserResponse {
  id: number;
  username: string;
  full_name: string | null;
  email: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string | null;
}

export interface UserListResponse {
  total: number;
  users: UserResponse[];
}

export interface CreateUserRequest {
  username: string;
  password: string;
  full_name?: string;
  email?: string;
  is_admin?: boolean;
}

export interface UpdateUserRequest {
  full_name?: string;
  email?: string;
  is_active?: boolean;
  is_admin?: boolean;
}

export const getUsers = async (): Promise<UserListResponse> => {
  const response = await apiClient.get<UserListResponse>('/users/');
  return response.data;
};

export const createUser = async (data: CreateUserRequest): Promise<UserResponse> => {
  const response = await apiClient.post<UserResponse>('/users/', data);
  return response.data;
};

export const updateUser = async (userId: number, data: UpdateUserRequest): Promise<UserResponse> => {
  const response = await apiClient.put<UserResponse>(`/users/${userId}`, data);
  return response.data;
};

export const updateUserPassword = async (userId: number, newPassword: string): Promise<void> => {
  await apiClient.put(`/users/${userId}/password`, { new_password: newPassword });
};

export const deleteUser = async (userId: number): Promise<void> => {
  await apiClient.delete(`/users/${userId}`);
};
