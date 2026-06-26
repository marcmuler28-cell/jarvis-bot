import React from 'react';
import './StatusIndicator.css';

const StatusIndicator = ({ status }) => {
  const getColor = () => {
    switch (status) {
      case 'desconectado': return '#c0392b';
      case 'inactivo': return '#6b7280';
      case 'escuchando': return '#3b82f6';
      case 'procesando': return '#eab308';
      case 'hablando': return '#10b981';
      default: return '#6b7280';
    }
  };

  const normalized = status === 'desconectado' ? 'offline' : status;

  return (
    <div className="status-indicator">
      <div
        className={`status-circle ${status === 'escuchando' || status === 'hablando' ? 'pulsing' : ''}`}
        style={{ backgroundColor: getColor() }}
      ></div>
      <span className="status-text">{normalized}</span>
    </div>
  );
};

export default StatusIndicator;