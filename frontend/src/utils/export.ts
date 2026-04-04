/**
 * Export utilities for data and reports
 */

export const exportToCSV = (data: any[], filename: string) => {
  if (data.length === 0) return;

  const headers = Object.keys(data[0]);
  const csvContent = [
    headers.join(','),
    ...data.map((row) =>
      headers.map((header) => {
        const value = row[header];
        if (value === null || value === undefined) return '';
        if (typeof value === 'string' && value.includes(',')) {
          return `"${value}"`;
        }
        return value;
      }).join(',')
    ),
  ].join('\n');

  downloadFile(csvContent, filename, 'text/csv');
};

export const exportToJSON = (data: any, filename: string) => {
  const jsonContent = JSON.stringify(data, null, 2);
  downloadFile(jsonContent, filename, 'application/json');
};

export const exportChartToImage = async (chartId: string, filename: string) => {
  const chartElement = document.getElementById(chartId);
  if (!chartElement) {
    console.error('Chart element not found');
    return;
  }

  try {
    // This would require html2canvas library
    // For now, we'll just show a message
    alert('Chart export feature requires html2canvas library. Install with: npm install html2canvas');
  } catch (error) {
    console.error('Error exporting chart:', error);
  }
};

export const generatePDFReport = (data: any, filename: string) => {
  // This would require jsPDF library
  // For now, we'll export as JSON
  alert('PDF export feature requires jsPDF library. Install with: npm install jspdf');
  exportToJSON(data, filename.replace('.pdf', '.json'));
};

const downloadFile = (content: string, filename: string, mimeType: string) => {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};
