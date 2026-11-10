-- Dump sintetico da isca (dados falsos)
CREATE TABLE clientes (
  id INT PRIMARY KEY,
  nome VARCHAR(100),
  email VARCHAR(120),
  cpf VARCHAR(14)
);
INSERT INTO clientes VALUES (1, 'Fulano de Tal', 'fulano@exemplo.invalid', '000.000.000-00');
