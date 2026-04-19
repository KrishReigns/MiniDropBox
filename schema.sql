CREATE DATABASE IF NOT EXISTS MiniDropbox;
USE MiniDropbox;

CREATE TABLE IF NOT EXISTS users (
  user_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  phone VARCHAR(50),
  email VARCHAR(255) NOT NULL UNIQUE,
  password VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS folders (
  folder_id INT AUTO_INCREMENT PRIMARY KEY,
  folder_name VARCHAR(255) NOT NULL,
  user_id INT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS files (
  file_id INT AUTO_INCREMENT PRIMARY KEY,
  file VARCHAR(511) NOT NULL,
  folder_id INT NOT NULL,
  status VARCHAR(100) NOT NULL,
  file_type VARCHAR(50),
  file_name VARCHAR(255) NOT NULL,
  file_size BIGINT DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (folder_id) REFERENCES folders(folder_id)
);

CREATE TABLE IF NOT EXISTS recycle_bin (
  recycle_id INT AUTO_INCREMENT PRIMARY KEY,
  delete_date DATE,
  date DATE,
  file_id INT NOT NULL,
  FOREIGN KEY (file_id) REFERENCES files(file_id)
);

CREATE TABLE IF NOT EXISTS downloads (
  download_id INT AUTO_INCREMENT PRIMARY KEY,
  date DATETIME,
  user_id INT NOT NULL,
  file_id INT NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(user_id),
  FOREIGN KEY (file_id) REFERENCES files(file_id)
);

CREATE TABLE IF NOT EXISTS shares (
  share_id INT AUTO_INCREMENT PRIMARY KEY,
  date DATETIME,
  shared_by_user_id INT NOT NULL,
  shared_to_user_id INT NOT NULL,
  file_id INT NOT NULL,
  FOREIGN KEY (shared_by_user_id) REFERENCES users(user_id),
  FOREIGN KEY (shared_to_user_id) REFERENCES users(user_id),
  FOREIGN KEY (file_id) REFERENCES files(file_id)
);

-- Storage quotas table
CREATE TABLE IF NOT EXISTS storage_quotas (
  quota_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL UNIQUE,
  quota_bytes BIGINT NOT NULL DEFAULT 1073741824, -- 1GB default
  used_bytes BIGINT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Activity logs table for audit trail
CREATE TABLE IF NOT EXISTS activity_logs (
  log_id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT,
  action VARCHAR(100) NOT NULL,
  resource_type VARCHAR(50), -- 'file', 'folder', 'user', etc.
  resource_id INT,
  details JSON,
  ip_address VARCHAR(45),
  user_agent TEXT,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_user_timestamp (user_id, timestamp),
  INDEX idx_action (action),
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);
