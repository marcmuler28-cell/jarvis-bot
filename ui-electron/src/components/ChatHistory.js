import React from 'react';
import './ChatHistory.css';

const ChatHistory = ({ history }) => {
  return (
    <div className="chat-history">
      {history.map((msg, index) => (
        <div key={index} className={`message ${msg.type}`}>
          <div className="message-bubble">
            {msg.text}
          </div>
        </div>
      ))}
    </div>
  );
};

export default ChatHistory;