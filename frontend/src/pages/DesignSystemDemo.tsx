import React, { useState } from 'react';
import {
  Button,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  Input,
  Select,
  Badge,
  Tabs,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Spinner,
} from '../components/ui';
import { useTheme } from '../hooks/useTheme';

/**
 * Demo page to showcase the design system components
 * This page demonstrates all UI components following the Subsurface Production Allocation design system
 */
export const DesignSystemDemo: React.FC = () => {
  const { theme, toggleTheme } = useTheme();
  const [activeTab, setActiveTab] = useState('tab1');
  const [isModalOpen, setIsModalOpen] = useState(false);

  const tabs = [
    { id: 'tab1', label: 'Components' },
    { id: 'tab2', label: 'Colors' },
    { id: 'tab3', label: 'Typography' },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '28px', fontWeight: 700, color: 'var(--color-text)', marginBottom: '8px' }}>
          Design System Demo
        </h1>
        <p style={{ fontSize: '14px', color: 'var(--color-text-muted)' }}>
          Showcase of all UI components following the Subsurface Production Allocation design system
        </p>
      </div>

      {/* Theme Toggle */}
      <Card padding="md" style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--color-text)', marginBottom: '4px' }}>
              Current Theme: {theme === 'dark' ? 'Dark' : 'Light'}
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--color-text-muted)' }}>
              Click the button to toggle between themes
            </p>
          </div>
          <Button onClick={toggleTheme} variant="primary">
            {theme === 'dark' ? '☀️ Light Mode' : '🌙 Dark Mode'}
          </Button>
        </div>
      </Card>

      {/* Tabs Demo */}
      <Tabs tabs={tabs} activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Tab Content */}
      {activeTab === 'tab1' && (
        <div style={{ display: 'grid', gap: '24px' }}>
          {/* Buttons */}
          <Card padding="lg">
            <CardHeader>
              <CardTitle>Buttons</CardTitle>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                <Button variant="primary" size="sm">Primary Small</Button>
                <Button variant="primary" size="md">Primary Medium</Button>
                <Button variant="primary" size="lg">Primary Large</Button>
                <Button variant="secondary">Secondary</Button>
                <Button variant="danger">Danger</Button>
                <Button variant="ghost">Ghost</Button>
                <Button variant="primary" disabled>Disabled</Button>
                <Button variant="primary" isLoading>Loading</Button>
              </div>
            </CardContent>
          </Card>

          {/* Badges */}
          <Card padding="lg">
            <CardHeader>
              <CardTitle>Badges</CardTitle>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <Badge variant="success">Success</Badge>
                <Badge variant="warning">Warning</Badge>
                <Badge variant="danger">Danger</Badge>
                <Badge variant="primary">Primary</Badge>
                <Badge variant="muted">Muted</Badge>
                <Badge variant="purple">Purple</Badge>
              </div>
            </CardContent>
          </Card>

          {/* Inputs */}
          <Card padding="lg">
            <CardHeader>
              <CardTitle>Form Inputs</CardTitle>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'grid', gap: '16px', maxWidth: '400px' }}>
                <Input label="Username" placeholder="Enter username" />
                <Input label="Email" type="email" placeholder="Enter email" />
                <Input label="Error State" error="This field is required" />
                <Input label="With Helper" helperText="This is a helper text" />
                <Select
                  label="Select Option"
                  options={[
                    { value: '1', label: 'Option 1' },
                    { value: '2', label: 'Option 2' },
                    { value: '3', label: 'Option 3' },
                  ]}
                />
              </div>
            </CardContent>
          </Card>

          {/* Modal Demo */}
          <Card padding="lg">
            <CardHeader>
              <CardTitle>Modal</CardTitle>
            </CardHeader>
            <CardContent>
              <Button onClick={() => setIsModalOpen(true)}>Open Modal</Button>
            </CardContent>
          </Card>

          {/* Spinner */}
          <Card padding="lg">
            <CardHeader>
              <CardTitle>Spinner</CardTitle>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                <Spinner size={24} />
                <Spinner size={32} />
                <Spinner size={48} />
              </div>
            </CardContent>
          </Card>

          {/* Status Messages */}
          <Card padding="lg">
            <CardHeader>
              <CardTitle>Status Messages</CardTitle>
            </CardHeader>
            <CardContent>
              <div style={{ display: 'grid', gap: '12px' }}>
                <div className="status-message success">
                  ✓ Operation completed successfully
                </div>
                <div className="status-message warning">
                  ⚠ Warning: Please review your data
                </div>
                <div className="status-message error">
                  ✗ Error: Something went wrong
                </div>
                <div className="status-message info">
                  ℹ Information: This is an informational message
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {activeTab === 'tab2' && (
        <Card padding="lg">
          <CardHeader>
            <CardTitle>Color Palette</CardTitle>
          </CardHeader>
          <CardContent>
            <div style={{ display: 'grid', gap: '24px' }}>
              {/* Chart Colors */}
              <div>
                <h4 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text)', marginBottom: '12px' }}>
                  Chart Palette (8 colors)
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '12px' }}>
                  {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
                    <div key={i} style={{ textAlign: 'center' }}>
                      <div
                        style={{
                          width: '100%',
                          height: '80px',
                          background: `var(--color-chart-${i})`,
                          borderRadius: 'var(--radius)',
                          marginBottom: '8px',
                        }}
                      />
                      <p style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>
                        Chart {i}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Status Colors */}
              <div>
                <h4 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text)', marginBottom: '12px' }}>
                  Status Colors
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: '12px' }}>
                  {['primary', 'success', 'warning', 'danger'].map((color) => (
                    <div key={color} style={{ textAlign: 'center' }}>
                      <div
                        style={{
                          width: '100%',
                          height: '80px',
                          background: `var(--color-${color})`,
                          borderRadius: 'var(--radius)',
                          marginBottom: '8px',
                        }}
                      />
                      <p style={{ fontSize: '12px', color: 'var(--color-text-muted)', textTransform: 'capitalize' }}>
                        {color}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {activeTab === 'tab3' && (
        <Card padding="lg">
          <CardHeader>
            <CardTitle>Typography</CardTitle>
          </CardHeader>
          <CardContent>
            <div style={{ display: 'grid', gap: '16px' }}>
              <div>
                <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--color-text)' }}>
                  Heading 1 - 22px Bold
                </h1>
              </div>
              <div>
                <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-text)' }}>
                  Heading 2 - 20px Bold
                </h2>
              </div>
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--color-text)' }}>
                  Heading 3 - 16px Semibold
                </h3>
              </div>
              <div>
                <h4 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--color-text)' }}>
                  Heading 4 - 14px Semibold
                </h4>
              </div>
              <div>
                <p style={{ fontSize: '14px', color: 'var(--color-text)' }}>
                  Body text - 14px Regular
                </p>
              </div>
              <div>
                <p style={{ fontSize: '13px', color: 'var(--color-text-muted)' }}>
                  Small text - 13px Muted
                </p>
              </div>
              <div>
                <p style={{ fontSize: '11px', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                  Micro text - 11px Uppercase
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Modal */}
      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)}>
        <ModalHeader onClose={() => setIsModalOpen(false)}>
          Example Modal
        </ModalHeader>
        <ModalBody>
          <p style={{ color: 'var(--color-text)', marginBottom: '16px' }}>
            This is an example modal following the design system guidelines.
          </p>
          <Input label="Name" placeholder="Enter your name" />
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setIsModalOpen(false)}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => setIsModalOpen(false)}>
            Save
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
};
