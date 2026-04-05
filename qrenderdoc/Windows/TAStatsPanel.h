/******************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2024-2026 Baldur Karlsson
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 ******************************************************************************/

#pragma once

#include <QFrame>
#include "Code/Interface/QRDInterface.h"

namespace Ui
{
class TAStatsPanel;
}

class QSortFilterProxyModel;
class QStandardItemModel;

class TAStatsPanel : public QFrame, public ITAStatsPanel, public ICaptureViewer
{
  Q_OBJECT

public:
  explicit TAStatsPanel(ICaptureContext &ctx, QWidget *parent = 0);
  ~TAStatsPanel();

  // ITAStatsPanel
  QWidget *Widget() override { return this; }

  // ICaptureViewer
  void OnCaptureLoaded() override;
  void OnCaptureClosed() override;
  void OnSelectedEventChanged(uint32_t eventId) override {}
  void OnEventChanged(uint32_t eventId) override {}

private slots:
  void on_groupMode_currentIndexChanged(int index);
  void on_filterText_textChanged(const QString &text);
  void on_statsTree_doubleClicked(const QModelIndex &index);

private:
  Ui::TAStatsPanel *ui;
  ICaptureContext &m_Ctx;

  QStandardItemModel *m_Model = nullptr;
  QSortFilterProxyModel *m_ProxyModel = nullptr;

  // Summary stats
  uint32_t m_TotalDrawCalls = 0;
  uint64_t m_TotalTriangles = 0;
  uint64_t m_TotalVertices = 0;
  uint64_t m_TotalInstances = 0;
  uint32_t m_TotalDispatches = 0;

  void CollectStats();
  void PopulateByPass();
  void PopulateByShader();
  void PopulateByRenderTarget();
  void UpdateSummary();
  void ClearStats();

  uint64_t CalcTriangles(const ActionDescription &action);
};
