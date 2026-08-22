import React from 'react';

interface CollapsibleSectionProps {
  title: string;
  children: React.ReactNode;
}

export const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({ title, children }) => (
  <details className="collapsible-section">
    <summary>{title}</summary>
    <div className="collapsible-content">{children}</div>
  </details>
);
