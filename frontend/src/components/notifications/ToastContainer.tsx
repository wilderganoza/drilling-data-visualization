/**
 * Toast Container Component - Manages multiple toasts
 */
import React from 'react';
import { Toast, ToastType } from './Toast';
import { useAppStore } from '../../store/appStore';

export interface ToastMessage {
  id: string;
  message: string;
  type: ToastType;
}

export const ToastContainer: React.FC = () => {
  const { toasts, removeToast } = useAppStore();

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2">
      {toasts.map((toast) => (
        <Toast
          key={toast.id}
          message={toast.message}
          type={toast.type}
          onClose={() => removeToast(toast.id)}
        />
      ))}
    </div>
  );
};
