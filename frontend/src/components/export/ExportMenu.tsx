/**
 * Export Menu Component - Download data and reports
 */
import React, { useState } from 'react';
import { Button } from '../ui';
import { exportToCSV, exportToJSON, generatePDFReport } from '../../utils/export';

interface ExportMenuProps {
  data: any;
  wellName: string;
  dataType: 'drilling' | 'events' | 'quality';
}

export const ExportMenu: React.FC<ExportMenuProps> = ({ data, wellName, dataType }) => {
  const [isOpen, setIsOpen] = useState(false);

  const handleExportCSV = () => {
    if (!data) return;
    
    const filename = `${wellName}_${dataType}_${new Date().toISOString().split('T')[0]}.csv`;
    
    if (Array.isArray(data)) {
      exportToCSV(data, filename);
    } else if (data.data && Array.isArray(data.data)) {
      exportToCSV(data.data, filename);
    } else {
      alert('No exportable data available');
    }
    setIsOpen(false);
  };

  const handleExportJSON = () => {
    if (!data) return;
    
    const filename = `${wellName}_${dataType}_${new Date().toISOString().split('T')[0]}.json`;
    exportToJSON(data, filename);
    setIsOpen(false);
  };

  const handleExportPDF = () => {
    const filename = `${wellName}_${dataType}_report_${new Date().toISOString().split('T')[0]}.pdf`;
    generatePDFReport(data, filename);
    setIsOpen(false);
  };

  return (
    <div className="relative">
      <Button
        variant="secondary"
        onClick={() => setIsOpen(!isOpen)}
      >
        📥 Export
      </Button>

      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />

          {/* Menu */}
          <div className="absolute right-0 mt-2 w-48 bg-gray-800 border border-gray-700 rounded-lg shadow-lg z-20">
            <div className="py-1">
              <button
                onClick={handleExportCSV}
                className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
              >
                📄 Export as CSV
              </button>
              <button
                onClick={handleExportJSON}
                className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
              >
                📋 Export as JSON
              </button>
              <button
                onClick={handleExportPDF}
                className="w-full text-left px-4 py-2 text-sm text-gray-300 hover:bg-gray-700 hover:text-white"
              >
                📑 Export as PDF
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
