import React from 'react';
import './Controls.css';

const Controls = ({ connected, onNewConversation, onClearHistory }) => {
  return (
    <div className="controls">
      <button className="btn secondary" onClick={onNewConversation} disabled={!connected}>
        Nueva conversación
      </button>
      <button className="btn secondary" onClick={onClearHistory} disabled={!connected}>
        Limpiar historial
      </button>
      <button className="btn secondary" disabled>
        Configuración
      </button>
    </div>
  );
};

export default Controls;