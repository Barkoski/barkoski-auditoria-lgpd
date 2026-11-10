<?php
session_start();
error_log('Contato recebido: ' . print_r($_POST, true));
include __DIR__ . '/includes/header.php';
?>
<form method="post" action="/enviar.php">
  <input type="text" name="nome" placeholder="Seu nome">
  <input type="email" name="email">
  <input type="tel" name="telefone">
  <textarea name="mensagem"></textarea>
  <button type="submit">Enviar</button>
</form>
