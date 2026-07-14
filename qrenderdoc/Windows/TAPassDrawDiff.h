/******************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2026 Baldur Karlsson
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
 ******************************************************************************/

#pragma once

#include <QFrame>
#include <QTreeWidget>
#include "Code/Interface/QRDInterface.h"

class QSpinBox;
class QToolButton;
class QPushButton;

class TAPassDrawDiff : public QFrame, public ICaptureViewer
{
public:
  explicit TAPassDrawDiff(ICaptureContext &ctx, QWidget *parent = 0);
  ~TAPassDrawDiff();

  QWidget *Widget() { return this; }

  void OnCaptureLoaded() override;
  void OnCaptureClosed() override;
  void OnSelectedEventChanged(uint32_t eventId) override {}
  void OnEventChanged(uint32_t eventId) override;

public:
  struct DiffRow
  {
    QString category;
    QString name;
    QString a;
    QString b;
    bool different = false;
  };

private:
  void CaptureA();
  void CaptureB();
  void Refresh();
  void ExportCSV();
  void ExportSnapshot();
  void ImportSnapshot();
  void GatherRowsForCurrentEvent(IReplayController *r, uint32_t eventId, rdcarray<DiffRow> &rows);
  void AddRow(rdcarray<DiffRow> &rows, const QString &category, const QString &name,
              const QString &a, const QString &b) const;
  void ApplyRows(const rdcarray<DiffRow> &rows);

  ICaptureContext &m_Ctx;
  QSpinBox *m_EventA = NULL;
  QSpinBox *m_EventB = NULL;
  QToolButton *m_SetA = NULL;
  QToolButton *m_SetB = NULL;
  QToolButton *m_Refresh = NULL;
  QToolButton *m_Export = NULL;
  QToolButton *m_ExportSnapshot = NULL;
  QToolButton *m_ImportSnapshot = NULL;
  QTreeWidget *m_Tree = NULL;
  QPushButton *m_ClearImported = NULL;
  rdcarray<DiffRow> m_ImportedRows;
};